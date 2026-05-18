# -*- coding: utf-8 -*-
"""
Chatbot Agent — tổng hợp toàn bộ context và sinh response Markdown tiếng Việt
bằng Gemini (streaming mode).
"""
import asyncio
import json
import logging
import re
import time

from openai import OpenAI

from app.core.config import settings
from app.core.prompts import CHATBOT_RESPONSE_PROMPT
from app.models.schemas import AgentState

logger = logging.getLogger(__name__)

_openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

_FALLBACK_RESPONSE = (
    "Xin lỗi, tôi gặp sự cố kỹ thuật khi xử lý yêu cầu của bạn.\n\n"
    "⚠️ **Lưu ý quan trọng**: Nếu bạn đang có vấn đề sức khỏe cần giải quyết, "
    "vui lòng liên hệ trực tiếp với bác sĩ hoặc đến cơ sở y tế gần nhất."
)

_INSUFFICIENT_CONTEXT_RESPONSE = (
    "Xin lỗi, hiện tại tôi **chưa có đủ thông tin** trong cơ sở dữ liệu y tế "
    "để trả lời chính xác cho câu hỏi của bạn.\n\n"
    "Bạn có thể thử:\n"
    "- Mô tả **chi tiết hơn** về triệu chứng (vị trí, thời gian xuất hiện, mức độ đau...).\n"
    "- Cung cấp thêm **bối cảnh** (tuổi, tiền sử bệnh, thuốc đang dùng).\n"
    "- Đính kèm **hình ảnh** nếu có liên quan đến vấn đề da liễu, chấn thương...\n\n"
    "⚠️ **Lưu ý**: Nếu vấn đề khẩn cấp hoặc kéo dài, vui lòng liên hệ trực tiếp "
    "với bác sĩ hoặc đến cơ sở y tế gần nhất để được tư vấn chính xác."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_retry_delay(exc: Exception, default: int = 65) -> int:
    """Lấy retry delay từ thông báo lỗi 429, fallback về default."""
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", str(exc))
    return int(match.group(1)) + 5 if match else default


def _call_openai_stream(prompt: str, max_retries: int = 2) -> str:
    """Gọi OpenAI với stream=True, thu thập toàn bộ chunks, auto-retry khi 429."""
    for attempt in range(max_retries + 1):
        try:
            stream = _openai_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": CHATBOT_RESPONSE_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                stream=True,
                stream_options={"include_usage": True},
            )
            parts: list[str] = []
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    parts.append(chunk.choices[0].delta.content)
            return "".join(parts)
        except Exception as exc:
            if "429" in str(exc) and attempt < max_retries:
                delay = _get_retry_delay(exc)
                logger.warning("Rate limit 429, thử lại sau %ds (lần %d/%d)", delay, attempt + 1, max_retries)
                time.sleep(delay)
            else:
                raise


def _build_user_prompt(state: AgentState) -> str:
    """Tổng hợp tất cả context thành prompt gửi cho Gemini."""
    sections: list[str] = []

    # thêm lịch sử chat vào prompt
    history = state.get("chat_history", [])
    if history:
        hist_lines = []
        for msg in history:
            who = "Người dùng" if msg.get("role") == "user" else "Trợ lý y tế"
            # Đánh dấu nếu turn cũ có kèm ảnh — giúp LLM hiểu được khi user
            # follow-up dạng "ảnh trên là bệnh gì?".
            n_imgs = len(msg.get("image_urls") or [])
            tag = f" [đã gửi {n_imgs} ảnh]" if n_imgs else ""
            hist_lines.append(f"**{who}{tag}:** {msg.get('content', '')}")

            # Phase 2: inject cached image_analysis của turn cũ vào prompt
            # (giúp LLM trả lời follow-up mà không cần gọi lại Vision API).
            cached = msg.get("image_analysis") or []
            for i, analysis in enumerate(cached, start=1):
                if not isinstance(analysis, dict):
                    continue
                summary = analysis.get("summary", "")
                severity = analysis.get("severity", "")
                if summary or severity:
                    hist_lines.append(
                        f"  > _Ảnh #{i} (đã phân tích trước đó):_ "
                        f"{summary} (mức độ: {severity})"
                    )
        sections.append("## Lịch sử trò chuyện:\n" + "\n".join(hist_lines))
        logger.info(
            "[Memory] Inject %d tin nhắn lịch sử vào prompt OpenAI", len(history)
        )
    else:
        logger.info("[Memory] Không có lịch sử — session mới hoặc rỗng")
        
    # Câu hỏi gốc
    sections.append(f"## Câu hỏi của người dùng:\n{state.get('user_message', '')}")

    # Thông tin y tế từ RAG
    rag_context = state.get("rag_context", "")
    if rag_context:
        sections.append(f"## Thông tin y tế từ tài liệu tham khảo:\n{rag_context}")

    # Kết quả phân tích ảnh — list[dict] (multi-image) hoặc dict đơn lẻ (legacy)
    image_result = state.get("image_analysis_result")
    results_list: list[dict] = []
    if isinstance(image_result, list):
        results_list = [r for r in image_result if isinstance(r, dict)]
    elif isinstance(image_result, dict):
        results_list = [image_result]

    if results_list:
        if len(results_list) == 1:
            r = results_list[0]
            img_section_parts = ["## Kết quả phân tích hình ảnh y tế:"]
            if r.get("summary"):
                img_section_parts.append(f"**Tóm tắt**: {r['summary']}")
            if r.get("findings"):
                img_section_parts.append(
                    "**Phát hiện**:\n" + "\n".join(f"- {f}" for f in r["findings"])
                )
            if r.get("severity"):
                img_section_parts.append(f"**Mức độ**: {r['severity']}")
            if r.get("urgency"):
                img_section_parts.append(f"**Độ khẩn**: {r['urgency']}")
            sections.append("\n".join(img_section_parts))
        else:
            multi_parts = [f"## Kết quả phân tích {len(results_list)} hình ảnh y tế:"]
            for i, r in enumerate(results_list, start=1):
                multi_parts.append(f"### Ảnh #{i}")
                if r.get("summary"):
                    multi_parts.append(f"- **Tóm tắt**: {r['summary']}")
                if r.get("findings"):
                    multi_parts.append(
                        "- **Phát hiện**: "
                        + "; ".join(str(f) for f in r["findings"])
                    )
                if r.get("severity"):
                    multi_parts.append(f"- **Mức độ**: {r['severity']}")
                if r.get("urgency"):
                    multi_parts.append(f"- **Độ khẩn**: {r['urgency']}")
            sections.append("\n".join(multi_parts))

    # Kết quả phân tích y tế (treatment_data)
    treatment_data = state.get("treatment_data")
    if treatment_data and isinstance(treatment_data, dict):
        td_section_parts: list[str] = ["## Phân tích y tế:"]

        conditions = treatment_data.get("possible_conditions", [])
        if conditions:
            td_section_parts.append(
                "**Tình trạng có thể**:\n" + "\n".join(f"- {c}" for c in conditions)
            )

        symptoms = treatment_data.get("symptoms", [])
        if symptoms:
            td_section_parts.append(
                "**Triệu chứng ghi nhận**:\n" + "\n".join(f"- {s}" for s in symptoms)
            )

        specialty = treatment_data.get("recommended_specialty", "")
        if specialty:
            td_section_parts.append(f"**Chuyên khoa khuyến nghị**: {specialty}")

        urgency = treatment_data.get("urgency", "routine")
        urgency_labels = {
            "routine": "Bình thường — có thể đặt lịch khám thông thường",
            "urgent": "⚠️ Khẩn — nên khám trong vòng 24-48 giờ",
            "emergency": "🚨 CẤP CỨU — cần đến bệnh viện NGAY LẬP TỨC",
        }
        td_section_parts.append(f"**Mức độ ưu tiên**: {urgency_labels.get(urgency, urgency)}")

        immediate = treatment_data.get("immediate_actions", [])
        if immediate:
            td_section_parts.append(
                "**Cần làm ngay**:\n" + "\n".join(f"- {a}" for a in immediate)
            )

        sections.append("\n".join(td_section_parts))

    sections.append(
        "Hãy tổng hợp toàn bộ thông tin trên và trả lời người dùng bằng tiếng Việt, "
        "rõ ràng, đồng cảm, theo định dạng Markdown."
    )

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

def _log_agent3_inputs(state: AgentState) -> None:
    """Log toàn bộ dữ liệu đầu vào Agent 3 trước khi build prompt."""
    logger.info("=" * 70)
    logger.info("[Agent3-Input] BẮT ĐẦU log dữ liệu gửi vào chatbot agent")
    logger.info("=" * 70)

    # 1. Câu hỏi hiện tại
    user_msg = state.get("user_message", "")
    logger.info("[Agent3-Input] 1) user_message (%d chars): %s", len(user_msg), user_msg)

    # 2. Lịch sử hội thoại
    history = state.get("chat_history", []) or []
    logger.info("[Agent3-Input] 2) chat_history: %d tin nhắn", len(history))
    for i, m in enumerate(history, start=1):
        preview = (m.get("content", "") or "")[:120].replace("\n", " ")
        logger.info(
            "[Agent3-Input]    [%d] role=%s | %d chars | preview=%s",
            i, m.get("role"), len(m.get("content", "") or ""), preview,
        )

    # 3. RAG context
    rag = state.get("rag_context", "") or ""
    logger.info("[Agent3-Input] 3) rag_context: %d chars", len(rag))
    if rag:
        logger.info("[Agent3-Input]    preview: %s", rag[:300].replace("\n", " ") + ("..." if len(rag) > 300 else ""))

    # 4. Kết quả phân tích ảnh (list dict per-image)
    img = state.get("image_analysis_result")
    img_list: list[dict] = []
    if isinstance(img, list):
        img_list = [r for r in img if isinstance(r, dict)]
    elif isinstance(img, dict):
        img_list = [img]
    if img_list:
        logger.info("[Agent3-Input] 4) image_analysis_result: %d ảnh", len(img_list))
        for i, r in enumerate(img_list, start=1):
            logger.info("[Agent3-Input]    [Ảnh %d] summary  : %s", i, r.get("summary", ""))
            logger.info("[Agent3-Input]    [Ảnh %d] findings : %s", i, r.get("findings", []))
            logger.info("[Agent3-Input]    [Ảnh %d] severity : %s", i, r.get("severity", ""))
            logger.info("[Agent3-Input]    [Ảnh %d] urgency  : %s", i, r.get("urgency", ""))
    else:
        logger.info("[Agent3-Input] 4) image_analysis_result: KHÔNG CÓ ẢNH")

    # 5. Treatment data
    td = state.get("treatment_data")
    if td and isinstance(td, dict):
        logger.info("[Agent3-Input] 5) treatment_data:")
        logger.info("[Agent3-Input]    possible_conditions   : %s", td.get("possible_conditions", []))
        logger.info("[Agent3-Input]    symptoms              : %s", td.get("symptoms", []))
        logger.info("[Agent3-Input]    severity              : %s", td.get("severity", ""))
        logger.info("[Agent3-Input]    body_parts            : %s", td.get("body_parts", []))
        logger.info("[Agent3-Input]    recommended_specialty : %s", td.get("recommended_specialty", ""))
        logger.info("[Agent3-Input]    urgency               : %s", td.get("urgency", ""))
        logger.info("[Agent3-Input]    immediate_actions     : %s", td.get("immediate_actions", []))
    else:
        logger.info("[Agent3-Input] 5) treatment_data: KHÔNG CÓ")

    # 6. Sources (không vào prompt nhưng vẫn log để debug)
    sources = state.get("sources", []) or []
    logger.info("[Agent3-Input] 6) sources (chỉ để trả về client): %d chunks", len(sources))

    logger.info("=" * 70)


async def generate_response(state: AgentState) -> AgentState:
    """
    LangGraph node: tổng hợp context và sinh response với Gemini streaming.

    Set state["response"] với nội dung Markdown tiếng Việt.
    """
    _log_agent3_inputs(state)

    # Chỉ trả fallback khi RAG rỗng VÀ không có chat_history để dựa vào.
    # Nếu có history → vẫn cho Gemini trả lời dựa trên ngữ cảnh hội thoại
    # (vd: user hỏi follow-up "tôi nên làm gì" sau khi đã nói "Tôi bị dị ứng").
    history = state.get("chat_history") or []
    if state.get("insufficient_context") and not history:
        logger.warning(
            "[Agent3] insufficient_context=True và không có chat_history → fallback, skip Gemini"
        )
        state["response"] = _INSUFFICIENT_CONTEXT_RESPONSE
        return state

    if state.get("insufficient_context") and history:
        logger.info(
            "[Agent3] RAG rỗng nhưng có %d tin nhắn lịch sử → vẫn gọi Gemini với context cũ",
            len(history),
        )

    prompt = _build_user_prompt(state)

    # Log toàn bộ prompt cuối cùng gửi cho Gemini
    logger.info("[Agent3-Prompt] Final prompt gửi OpenAI (%d chars):", len(prompt))
    logger.info("-" * 70)
    for line in prompt.split("\n"):
        logger.info("[Agent3-Prompt] %s", line)
    logger.info("-" * 70)

    loop = asyncio.get_running_loop()

    try:
        response_text = await loop.run_in_executor(None, _call_openai_stream, prompt)
        if not response_text.strip():
            response_text = _FALLBACK_RESPONSE
        state["response"] = response_text
        logger.info("Chatbot response OK (%d chars)", len(response_text))
    except Exception as exc:
        logger.error("Chatbot agent lỗi: %s", exc)
        state["response"] = _FALLBACK_RESPONSE

    return state
