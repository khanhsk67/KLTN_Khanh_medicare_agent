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
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role="user",
        content=state.get("user_message", ""),
    )
    db.add(user_msg)

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
) -> ChatResponse:
    """
    Entry point công khai — gọi từ chat route.

    Args:
        request: ChatRequest từ client (message, session_id, image_base64)
        user:    User ORM object (đã xác thực JWT)
        db:      AsyncSession từ FastAPI dependency

    Returns:
        ChatResponse với session_id, message_id, content, sources, urgency_level
    """
    # Chuẩn bị dữ liệu ảnh
    image_base64: str | None = None
    image_mime_type: str = "image/jpeg"
    if request.image_base64:
        image_mime_type = _detect_mime_type(request.image_base64)
        image_base64 = _strip_data_url(request.image_base64)

    initial_state: AgentState = {
        "user_id": str(user.id),
        "session_id": str(request.session_id) if request.session_id else None,
        "user_message": request.message,
        "image_base64": image_base64,
        "image_mime_type": image_mime_type,
        "image_analysis_result": None,
        "retrieved_chunks": [],
        "sources": [],
        "rag_context": "",
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
