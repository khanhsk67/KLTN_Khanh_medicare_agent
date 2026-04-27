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

import google.generativeai as genai

from app.core.config import settings
from app.core.prompts import CHATBOT_RESPONSE_PROMPT
from app.models.schemas import AgentState

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GOOGLE_API_KEY)

_FALLBACK_RESPONSE = (
    "Xin lỗi, tôi gặp sự cố kỹ thuật khi xử lý yêu cầu của bạn.\n\n"
    "⚠️ **Lưu ý quan trọng**: Nếu bạn đang có vấn đề sức khỏe cần giải quyết, "
    "vui lòng liên hệ trực tiếp với bác sĩ hoặc đến cơ sở y tế gần nhất."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_retry_delay(exc: Exception, default: int = 65) -> int:
    """Lấy retry delay từ thông báo lỗi 429, fallback về default."""
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", str(exc))
    return int(match.group(1)) + 5 if match else default


def _call_gemini_stream(prompt: str, max_retries: int = 2) -> str:
    """Gọi Gemini với stream=True, thu thập toàn bộ chunks, auto-retry khi 429."""
    model = genai.GenerativeModel(
        settings.LLM_MODEL,
        system_instruction=CHATBOT_RESPONSE_PROMPT,
    )
    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(prompt, stream=True)
            parts: list[str] = []
            for chunk in response:
                if chunk.text:
                    parts.append(chunk.text)
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

    # Câu hỏi gốc
    sections.append(f"## Câu hỏi của người dùng:\n{state.get('user_message', '')}")

    # Thông tin y tế từ RAG
    rag_context = state.get("rag_context", "")
    if rag_context:
        sections.append(f"## Thông tin y tế từ tài liệu tham khảo:\n{rag_context}")

    # Kết quả phân tích ảnh
    image_result = state.get("image_analysis_result")
    if image_result and isinstance(image_result, dict):
        img_summary = image_result.get("summary", "")
        img_findings = image_result.get("findings", [])
        img_severity = image_result.get("severity", "")
        img_urgency = image_result.get("urgency", "")

        img_section = "## Kết quả phân tích hình ảnh y tế:"
        if img_summary:
            img_section += f"\n**Tóm tắt**: {img_summary}"
        if img_findings:
            img_section += "\n**Phát hiện**:\n" + "\n".join(f"- {f}" for f in img_findings)
        if img_severity:
            img_section += f"\n**Mức độ**: {img_severity}"
        if img_urgency:
            img_section += f"\n**Độ khẩn**: {img_urgency}"
        sections.append(img_section)

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

async def generate_response(state: AgentState) -> AgentState:
    """
    LangGraph node: tổng hợp context và sinh response với Gemini streaming.

    Set state["response"] với nội dung Markdown tiếng Việt.
    """
    prompt = _build_user_prompt(state)
    loop = asyncio.get_running_loop()

    try:
        response_text = await loop.run_in_executor(None, _call_gemini_stream, prompt)
        if not response_text.strip():
            response_text = _FALLBACK_RESPONSE
        state["response"] = response_text
        logger.info("Chatbot response OK (%d chars)", len(response_text))
    except Exception as exc:
        logger.error("Chatbot agent lỗi: %s", exc)
        state["response"] = _FALLBACK_RESPONSE

    return state
