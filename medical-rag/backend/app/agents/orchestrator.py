# -*- coding: utf-8 -*-
"""
Orchestrator — LangGraph StateGraph điều phối toàn bộ pipeline y tế.

Flow: START → analyze_image → retrieve_rules → generate_response → persist_to_db → END

Hàm public: run_medical_graph(request, user, db) → ChatResponse
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chatbot_agent import generate_response
from app.agents.image_medical_agent import analyze_image
from app.agents.rule_medical_agent import retrieve_medical_rules
from app.db.models.chat_message import ChatMessage
from app.db.models.chat_session import ChatSession
from app.db.models.treatment_record import TreatmentRecord
from app.db.models.user import User
from app.models.schemas import AgentState, ChatRequest, ChatResponse, SourceChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_mime_type(image_base64: str) -> str:
    """Phát hiện MIME type từ data URL prefix hoặc magic bytes."""
    if image_base64.startswith("data:"):
        match = re.match(r"data:([^;]+);base64,", image_base64)
        if match:
            return match.group(1)
    # Phát hiện qua magic bytes
    import base64 as _b64
    try:
        raw = _b64.b64decode(image_base64[:20])
        if raw[:2] == b"\xff\xd8":
            return "image/jpeg"
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if raw[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return "image/webp"
    except Exception:
        pass
    return "image/jpeg"


def _strip_data_url(image_base64: str) -> str:
    """Bỏ phần 'data:image/xxx;base64,' nếu có."""
    if image_base64.startswith("data:"):
        return re.sub(r"^data:[^;]+;base64,", "", image_base64)
    return image_base64


# Regex phát hiện user đang tham chiếu ảnh đã gửi trước đó trong cùng phiên.
# Match một số cụm tiếng Việt phổ biến — không tham vọng bắt 100%,
# chỉ cần cover các pattern thường gặp khi user follow-up về ảnh.
_IMAGE_REFERENCE_REGEX = re.compile(
    r"(?:ảnh|hình|tấm)\s+(?:trên|kia|đó|này|vừa\s*rồi|trước|phía\s*trên|ở\s*trên|đính\s*kèm|ban\s*đầu|vừa\s*gửi)"
    r"|(?:ảnh|hình|tấm)\s+tôi(?:\s+(?:đã|vừa))?\s+gửi"
    r"|phân\s*tích\s+(?:lại\s+)?(?:ảnh|hình|tấm)"
    r"|xem\s*(?:lại|kĩ|kỹ)\s+(?:ảnh|hình|tấm)",
    re.IGNORECASE,
)


def _message_references_prior_image(text: str | None) -> bool:
    """True nếu user message có dấu hiệu đang nhắc tới ảnh đã gửi trước đó."""
    if not text:
        return False
    return bool(_IMAGE_REFERENCE_REGEX.search(text))


def _find_latest_images_in_history(history: list[dict]) -> list[str]:
    """Tìm danh sách data URL của user message gần nhất có ảnh. Rỗng nếu không có."""
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        urls = msg.get("image_urls") or []
        if urls:
            return list(urls)
    return []


# ---------------------------------------------------------------------------
# persist_to_db — lưu session, messages, treatment record
# ---------------------------------------------------------------------------

async def _persist_to_db(
    state: AgentState,
    user: User,
    db: AsyncSession,
) -> AgentState:
    """
    Lưu vào PostgreSQL:
    1. Tạo hoặc lấy ChatSession (kiểm tra user_id ownership)
    2. Lưu user message
    3. Lưu assistant response
    4. Tạo TreatmentRecord nếu có dữ liệu chẩn đoán
    """
    user_id: uuid.UUID = user.id

    # --- ChatSession ---
    chat_session: ChatSession | None = None
    raw_session_id = state.get("session_id")
    if raw_session_id:
        try:
            session_uuid = uuid.UUID(str(raw_session_id))
            result = await db.execute(
                select(ChatSession).where(
                    ChatSession.id == session_uuid,
                    ChatSession.user_id == user_id,
                )
            )
            chat_session = result.scalar_one_or_none()
        except (ValueError, Exception) as exc:
            logger.warning("Không tìm được session %s: %s", raw_session_id, exc)

    if chat_session is None:
        title = (state.get("user_message") or "")[:100] or "Cuộc tư vấn mới"
        chat_session = ChatSession(user_id=user_id, title=title)
        db.add(chat_session)
        await db.flush()  # lấy ID được gán bởi DB
    else:
        # Cập nhật updated_at để session luôn xuất hiện đầu danh sách
        chat_session.updated_at = datetime.now(timezone.utc)

    state["session_id"] = str(chat_session.id)

    # --- User message ---
    # Nếu ảnh được reuse từ history, không lưu lại image_urls cho message mới
    # (tránh duplicate base64 blob + tránh hiển thị cùng ảnh hai lần trong UI).
    images_b64: list[str] = state.get("images_base64") or []
    mime_types: list[str] = state.get("image_mime_types") or []
    reused = bool(state.get("reused_image_from_history"))

    image_urls: list[str] | None = None
    if images_b64 and not reused:
        image_urls = []
        for i, b64 in enumerate(images_b64):
            mime = mime_types[i] if i < len(mime_types) else "image/jpeg"
            image_urls.append(f"data:{mime};base64,{b64}")

    # Cache phân tích Vision cho fresh images (Phase 2). Skip khi reuse —
    # analysis cũ đã có sẵn trên message cũ.
    image_analysis_raw = state.get("image_analysis_result")
    image_analysis_to_save: list[dict[str, Any]] | None = None
    if image_analysis_raw and not reused:
        if isinstance(image_analysis_raw, list):
            image_analysis_to_save = image_analysis_raw
        elif isinstance(image_analysis_raw, dict):
            # Defensive: cũ là dict đơn lẻ — wrap vào list để đồng nhất schema
            image_analysis_to_save = [image_analysis_raw]

    user_msg = ChatMessage(
        session_id=chat_session.id,
        role="user",
        content=state.get("user_message", ""),
        image_urls=image_urls,
        image_analysis=image_analysis_to_save,
    )
    db.add(user_msg)
    await db.flush()  # ← Flush trước để user_msg có created_at sớm hơn assistant_msg

    # --- Assistant message ---
    sources: list[SourceChunk] = state.get("sources", [])
    sources_payload = [s.model_dump() for s in sources] if sources else None

    assistant_msg = ChatMessage(
        session_id=chat_session.id,
        role="assistant",
        content=state.get("response", ""),
        sources=sources_payload,
        urgency_level=state.get("urgency_level"),
    )
    db.add(assistant_msg)
    await db.flush()

    state["message_id"] = str(assistant_msg.id)

    # --- TreatmentRecord (nếu có dữ liệu chẩn đoán) ---
    treatment_data = state.get("treatment_data")
    if treatment_data and isinstance(treatment_data, dict):
        possible_conditions: list = treatment_data.get("possible_conditions", [])
        symptoms: list = treatment_data.get("symptoms", [])

        if possible_conditions or symptoms:
            # Tránh tạo record trùng cho cùng session
            existing = await db.execute(
                select(TreatmentRecord).where(
                    TreatmentRecord.session_id == chat_session.id
                )
            )
            if existing.scalar_one_or_none() is None:
                severity_raw = treatment_data.get("severity", "mild")
                severity = severity_raw if severity_raw in ("mild", "moderate", "severe") else "mild"

                record = TreatmentRecord(
                    user_id=user_id,
                    session_id=chat_session.id,
                    symptoms=symptoms,
                    possible_conditions=possible_conditions,
                    severity=severity,
                    body_parts=treatment_data.get("body_parts"),
                    recommended_specialty=treatment_data.get("recommended_specialty"),
                    urgency=treatment_data.get("urgency", "routine"),
                )
                db.add(record)

    await db.flush()

    # Commit ngay tại đây để đảm bảo data được lưu trước khi
    # SSE "done" event được gửi về client. Nếu không commit ở đây,
    # client sẽ gọi loadSessions() trước khi get_db dependency
    # cleanup (commit) chạy → session mới chưa thấy trong DB.
    await db.commit()

    return state


# ---------------------------------------------------------------------------
# Graph builder + entry point
# ---------------------------------------------------------------------------

def _build_graph(user: User, db: AsyncSession) -> object:
    """
    Xây dựng LangGraph StateGraph với closure inject user + db vào persist_node.
    Graph được build mới cho mỗi request (stateless).
    """
    async def persist_node(state: AgentState) -> AgentState:
        return await _persist_to_db(state, user, db)

    builder: StateGraph = StateGraph(AgentState)

    builder.add_node("analyze_image", analyze_image)
    builder.add_node("retrieve_rules", retrieve_medical_rules)
    builder.add_node("generate_response", generate_response)
    builder.add_node("persist_to_db", persist_node)

    builder.set_entry_point("analyze_image")
    builder.add_edge("analyze_image", "retrieve_rules")
    builder.add_edge("retrieve_rules", "generate_response")
    builder.add_edge("generate_response", "persist_to_db")
    builder.add_edge("persist_to_db", END)

    return builder.compile()


async def run_medical_graph(
    request: ChatRequest,
    user: User,
    db: AsyncSession,
    collection_alias: str | None = None,
) -> ChatResponse:
    """
    Entry point công khai — gọi từ chat route.

    Args:
        request:          ChatRequest từ client (message, session_id, image_base64)
        user:             User ORM object (đã xác thực JWT)
        db:               AsyncSession từ FastAPI dependency
        collection_alias: 'clean' | 'raw' | None — chọn collection RAG (A/B test)

    Returns:
        ChatResponse với session_id, message_id, content, sources, urgency_level
    """
    # Chuẩn bị dữ liệu ảnh — gộp images_base64 (mới) và image_base64 (legacy)
    raw_images: list[str] = []
    if request.images_base64:
        raw_images.extend(request.images_base64)
    if request.image_base64:
        raw_images.append(request.image_base64)

    images_base64: list[str] = []
    image_mime_types: list[str] = []
    for raw in raw_images:
        if not raw:
            continue
        images_base64.append(_strip_data_url(raw))
        image_mime_types.append(_detect_mime_type(raw))

    chat_history = await _load_chat_history(
        session_id=str(request.session_id) if request.session_id else None,
        db=db,
    )

    # Phase 1: nếu turn này không kèm ảnh mới nhưng user đang nhắc tới
    # ảnh đã gửi trước đó → reuse danh sách ảnh gần nhất trong history.
    reused_image = False
    if not images_base64 and _message_references_prior_image(request.message):
        prior_urls = _find_latest_images_in_history(chat_history)
        if prior_urls:
            for url in prior_urls:
                images_base64.append(_strip_data_url(url))
                image_mime_types.append(_detect_mime_type(url))
            reused_image = True
            logger.info(
                "[Image-Reuse] User nhắc tới ảnh cũ, reuse %d ảnh gần nhất",
                len(prior_urls),
            )
        else:
            logger.info(
                "[Image-Reuse] User nhắc tới ảnh nhưng history không có ảnh nào"
            )

    initial_state: AgentState = {
        "user_id": str(user.id),
        "session_id": str(request.session_id) if request.session_id else None,
        "user_message": request.message,
        "chat_history": chat_history,
        "images_base64": images_base64,
        "image_mime_types": image_mime_types,
        "reused_image_from_history": reused_image,
        "collection_alias": collection_alias,
        "image_analysis_result": None,
        "retrieved_chunks": [],
        "sources": [],
        "rag_context": "",
        "insufficient_context": False,
        "response": "",
        "message_id": None,
        "urgency_level": None,
        "treatment_data": None,
        "error": None,
        "iterations": 0,
    }

    graph = _build_graph(user, db)

    try:
        final_state: AgentState = await graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("LangGraph pipeline lỗi: %s", exc)
        # Trả về response lỗi tối giản — vẫn dùng session_id từ initial state nếu có
        return ChatResponse(
            session_id=request.session_id or uuid.uuid4(),
            message_id=uuid.uuid4(),
            content=(
                "Xin lỗi, hệ thống gặp sự cố. "
                "Vui lòng thử lại hoặc liên hệ bác sĩ trực tiếp."
            ),
            sources=[],
            urgency_level=None,
            created_at=datetime.utcnow(),
        )
    

    return ChatResponse(
        session_id=uuid.UUID(final_state["session_id"]),
        message_id=uuid.UUID(final_state["message_id"]),
        content=final_state.get("response", ""),
        sources=final_state.get("sources", []),
        urgency_level=final_state.get("urgency_level"),
        created_at=datetime.utcnow(),
    )

async def _load_chat_history(
    session_id: str | None,
    db: AsyncSession,
    limit: int = 10,
) -> list[dict]:
    """Đọc N tin nhắn gần nhất của session để làm context cho AI."""
    if not session_id:
        return []
    try:
        session_uuid = uuid.UUID(str(session_id))
    except ValueError:
        logger.warning("session_id không hợp lệ: %s", session_id)
        return []

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_uuid)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()  # Đảo ngược để có thứ tự thời gian (cũ → mới)

    # Bao gồm image_urls + image_analysis để có thể:
    # (a) Reuse ảnh cũ khi user follow-up không kèm ảnh mới
    # (b) Inject analysis cũ vào prompt mà không cần gọi lại Vision API
    history = [
        {
            "role": m.role,
            "content": m.content,
            "image_urls": list(m.image_urls or []),
            "image_analysis": list(m.image_analysis or []) if m.image_analysis else None,
        }
        for m in messages
    ]
    logger.info(
        "[Memory] Đã nạp %d tin nhắn cũ từ session %s", len(history), session_id
    )
    for idx, item in enumerate(history, start=1):
        preview = item["content"][:80].replace("\n", " ")
        n_imgs = len(item.get("image_urls") or [])
        has_analysis = "Y" if item.get("image_analysis") else "N"
        logger.info(
            "[Memory] %d/%d | role=%s | imgs=%d | analysis=%s | preview=%s",
            idx, len(history), item["role"], n_imgs, has_analysis, preview,
        )
    return history
    
    