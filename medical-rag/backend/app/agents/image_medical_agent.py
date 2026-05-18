# -*- coding: utf-8 -*-
"""
Image Medical Agent — phân tích hình ảnh y tế bằng OpenAI Vision.

Hỗ trợ multi-image / turn: phân tích song song N ảnh, trả về list dict.
"""
import asyncio
import base64
import json
import logging
import re
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.core.prompts import IMAGE_ANALYSIS_PROMPT
from app.models.schemas import AgentState

logger = logging.getLogger(__name__)

# Cấu hình client một lần khi module được import
_openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Helpers (sync — chạy trong thread executor)
# ---------------------------------------------------------------------------

def _call_openai_vision(image_bytes: bytes, mime_type: str) -> str:
    """Gọi OpenAI Vision API (sync) — sẽ được wrap bằng run_in_executor."""
    b64_str = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64_str}"
    response = _openai_client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": IMAGE_ANALYSIS_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )
    return response.choices[0].message.content


def _extract_json(text: str) -> dict[str, Any]:
    """Trích xuất JSON từ response text, bỏ qua markdown code block nếu có."""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def _fallback_result() -> dict[str, Any]:
    return {
        "findings": ["Không thể phân tích hình ảnh do lỗi hệ thống"],
        "severity": "mild",
        "urgency": "routine",
        "summary": "Lỗi phân tích ảnh — vui lòng mô tả triệu chứng bằng văn bản.",
    }


async def _analyze_single_image(
    image_bytes: bytes, mime_type: str, idx: int
) -> dict[str, Any]:
    """Phân tích 1 ảnh — retry 1 lần nếu fail."""
    loop = asyncio.get_running_loop()
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            raw_text = await loop.run_in_executor(
                None, _call_openai_vision, image_bytes, mime_type
            )
            result = _extract_json(raw_text)
            logger.info(
                "Image[%d] analysis OK (attempt %d): severity=%s, urgency=%s",
                idx, attempt + 1,
                result.get("severity"), result.get("urgency"),
            )
            return result
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning(
                "Image[%d] attempt %d — JSON parse lỗi: %s", idx, attempt + 1, exc
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Image[%d] attempt %d — OpenAI Vision lỗi: %s", idx, attempt + 1, exc
            )

    logger.error("Image[%d] analysis thất bại sau 2 lần: %s", idx, last_error)
    return _fallback_result()


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

async def analyze_image(state: AgentState) -> AgentState:
    """
    LangGraph node: phân tích danh sách hình ảnh y tế song song.

    - Nếu không có ảnh nào → bỏ qua, trả state nguyên.
    - Nếu ảnh là reuse từ history (Phase 2 Image-Reuse) → dùng cache
      image_analysis trong chat_messages, SKIP Vision API.
    - Ảnh mới: mỗi ảnh gọi Vision API riêng (parallel), retry 1 lần nếu fail.
    - state["image_analysis_result"] là list[dict] song song với images_base64.
    """
    images_b64: list[str] = state.get("images_base64") or []
    if not images_b64:
        state["image_analysis_result"] = None
        return state

    # ── Image-Reuse Phase 2 ──────────────────────────────────────────────────
    # Khi cờ reused_image_from_history=True, ảnh đã được phân tích trong một
    # lượt trước và kết quả đang được cache ở trường image_analysis JSONB của
    # bảng chat_messages. Dùng lại cache thay vì gọi Vision API — tiết kiệm
    # ~5-8s/ảnh và chi phí token đầu vào của Vision.
    # Nếu không tìm thấy cache (edge case: tin nhắn cũ tạo trước migration 004
    # hoặc cache bị clear), fallback gọi Vision lại để đảm bảo correctness.
    if state.get("reused_image_from_history"):
        chat_history = state.get("chat_history", []) or []
        for msg in reversed(chat_history):
            if msg.get("role") != "user":
                continue
            cached = msg.get("image_analysis")
            if cached:
                cached_list = cached if isinstance(cached, list) else [cached]
                logger.info(
                    "[Image-Reuse Phase 2] Skip Vision API — dùng cache %d analysis từ history",
                    len(cached_list),
                )
                state["image_analysis_result"] = cached_list
                return state
        logger.warning(
            "[Image-Reuse Phase 2] reused_image_from_history=True nhưng không "
            "tìm thấy image_analysis cache — fallback gọi Vision API lại"
        )

    mime_types: list[str] = state.get("image_mime_types") or []

    # Decode song song
    decoded: list[tuple[bytes, str, int]] = []
    for idx, b64 in enumerate(images_b64):
        mime = mime_types[idx] if idx < len(mime_types) else "image/jpeg"
        try:
            decoded.append((base64.b64decode(b64), mime, idx))
        except Exception as exc:
            logger.error("Image[%d] decode base64 lỗi: %s", idx, exc)
            decoded.append((b"", mime, idx))

    # Phân tích song song
    tasks = [
        _analyze_single_image(img_bytes, mime, idx) if img_bytes else
        asyncio.sleep(0, result=_fallback_result())
        for img_bytes, mime, idx in decoded
    ]
    results: list[dict[str, Any]] = list(await asyncio.gather(*tasks))

    state["image_analysis_result"] = results
    logger.info(
        "Tổng cộng %d ảnh đã phân tích | severities=%s",
        len(results), [r.get("severity") for r in results],
    )
    return state
