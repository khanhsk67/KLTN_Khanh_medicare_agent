# -*- coding: utf-8 -*-
"""
Image Medical Agent — phân tích hình ảnh y tế bằng Gemini Vision.
"""
import asyncio
import base64
import json
import logging
import re
from typing import Any

import google.generativeai as genai

from app.core.config import settings
from app.core.prompts import IMAGE_ANALYSIS_PROMPT
from app.models.schemas import AgentState

logger = logging.getLogger(__name__)

# Cấu hình API key một lần khi module được import
genai.configure(api_key=settings.GOOGLE_API_KEY)


# ---------------------------------------------------------------------------
# Helpers (sync — chạy trong thread executor)
# ---------------------------------------------------------------------------

def _call_gemini_vision(image_bytes: bytes, mime_type: str) -> str:
    """Gọi Gemini Vision API (sync) — sẽ được wrap bằng run_in_executor."""
    model = genai.GenerativeModel(settings.LLM_MODEL)
    response = model.generate_content(
        [
            {"mime_type": mime_type, "data": image_bytes},
            IMAGE_ANALYSIS_PROMPT,
        ]
    )
    return response.text


def _extract_json(text: str) -> dict[str, Any]:
    """Trích xuất JSON từ response text, bỏ qua markdown code block nếu có."""
    # Xóa ```json ... ``` hoặc ``` ... ```
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    # Tìm đoạn JSON đầu tiên nếu có text thừa
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

async def analyze_image(state: AgentState) -> AgentState:
    """
    LangGraph node: phân tích hình ảnh y tế.

    - Nếu không có image_base64 → bỏ qua, trả về state nguyên.
    - Gọi Gemini Vision → parse JSON → set state["image_analysis_result"].
    - Retry 1 lần nếu lần đầu thất bại.
    """
    if not state.get("image_base64"):
        state["image_analysis_result"] = None
        return state

    mime_type: str = state.get("image_mime_type") or "image/jpeg"

    try:
        image_bytes = base64.b64decode(state["image_base64"])
    except Exception as exc:
        logger.error("Không thể decode base64 ảnh: %s", exc)
        state["image_analysis_result"] = None
        state["error"] = f"Base64 decode error: {exc}"
        return state

    loop = asyncio.get_running_loop()
    last_error: Exception | None = None

    for attempt in range(2):  # lần 1 + retry 1
        try:
            raw_text = await loop.run_in_executor(
                None,
                _call_gemini_vision,
                image_bytes,
                mime_type,
            )
            result = _extract_json(raw_text)
            state["image_analysis_result"] = result
            logger.info(
                "Image analysis OK (attempt %d): severity=%s, urgency=%s",
                attempt + 1,
                result.get("severity"),
                result.get("urgency"),
            )
            logger.info("thông tin của Agent 1 sau khi phân tích hình ảnh là %s", state["image_analysis_result"])
            return state
            
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning("Attempt %d — JSON parse lỗi: %s", attempt + 1, exc)
        except Exception as exc:
            last_error = exc
            logger.warning("Attempt %d — Gemini Vision lỗi: %s", attempt + 1, exc)

    # Cả 2 lần đều thất bại — tiếp tục pipeline với result rỗng
    logger.error("Image analysis thất bại sau 2 lần: %s", last_error)
    state["image_analysis_result"] = {
        "findings": ["Không thể phân tích hình ảnh do lỗi hệ thống"],
        "severity": "mild",
        "urgency": "routine",
        "summary": "Lỗi phân tích ảnh — vui lòng mô tả triệu chứng bằng văn bản.",
    }
    return state
