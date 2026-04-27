# -*- coding: utf-8 -*-
"""
Rule Medical Agent — tìm kiếm tài liệu y tế (RAG) và phân tích với Gemini.
"""
import asyncio
import json
import logging
import re
import time
from typing import Any

import google.generativeai as genai

from app.core.config import settings
from app.core.prompts import RULE_MEDICAL_SYSTEM_PROMPT
from app.models.schemas import AgentState, SourceChunk
from app.services.vector_store import qdrant_service

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GOOGLE_API_KEY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_retry_delay(exc: Exception, default: int = 65) -> int:
    """Lấy retry delay từ thông báo lỗi 429, fallback về default."""
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", str(exc))
    return int(match.group(1)) + 5 if match else default


def _call_gemini_text(prompt: str, max_retries: int = 2) -> str:
    """Gọi Gemini text generation với auto-retry khi gặp 429."""
    model = genai.GenerativeModel(settings.LLM_MODEL)
    for attempt in range(max_retries + 1):
        try:
            return model.generate_content(prompt).text
        except Exception as exc:
            if "429" in str(exc) and attempt < max_retries:
                delay = _get_retry_delay(exc)
                logger.warning("Rate limit 429, thử lại sau %ds (lần %d/%d)", delay, attempt + 1, max_retries)
                time.sleep(delay)
            else:
                raise


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def _build_search_query(state: AgentState) -> str:
    """Kết hợp message + image findings thành query cho Qdrant."""
    parts: list[str] = []

    user_msg = state.get("user_message", "").strip()
    if user_msg:
        parts.append(user_msg)

    image_result = state.get("image_analysis_result")
    if image_result and isinstance(image_result, dict):
        findings = image_result.get("findings", [])
        conditions = image_result.get("suspected_conditions", [])
        body_parts = image_result.get("affected_body_parts", [])
        if findings:
            parts.append("Phát hiện: " + ", ".join(findings[:3]))
        if conditions:
            parts.append("Nghi ngờ: " + ", ".join(conditions[:2]))
        if body_parts:
            parts.append("Vị trí: " + ", ".join(body_parts[:2]))

    return " | ".join(parts) if parts else user_msg


def _format_chunks_for_prompt(chunks: list[SourceChunk]) -> str:
    if not chunks:
        return "Không tìm thấy tài liệu y tế liên quan."
    sections = []
    for i, chunk in enumerate(chunks, 1):
        header = f"[Tài liệu {i}: {chunk.source_file}"
        if chunk.page_number:
            header += f", trang {chunk.page_number}"
        header += f" — độ liên quan: {chunk.relevance_score:.2f}]"
        sections.append(f"{header}\n{chunk.content}")
    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

async def retrieve_medical_rules(state: AgentState) -> AgentState:
    """
    LangGraph node: RAG search + Gemini analysis.

    1. Build query từ message + image analysis
    2. Search Qdrant top-5 chunks
    3. Gọi Gemini với chunks + RULE_MEDICAL_SYSTEM_PROMPT
    4. Parse JSON → set state["rag_context"], ["treatment_data"], ["urgency_level"]
    """
    query = _build_search_query(state)
    logger.info("RAG query: %s", query[:100])

    # Tìm kiếm tài liệu y tế
    try:
        chunks = await qdrant_service.search(query, top_k=5)
    except Exception as exc:
        logger.error("Qdrant search lỗi: %s", exc)
        chunks = []

    state["retrieved_chunks"] = chunks
    state["sources"] = chunks

    # Format chunks thành context text
    chunks_text = _format_chunks_for_prompt(chunks)

    # Build image analysis section
    image_section = ""
    image_result = state.get("image_analysis_result")
    if image_result and isinstance(image_result, dict):
        image_section = (
            "\n\n## Kết quả phân tích hình ảnh y tế:\n"
            + json.dumps(image_result, ensure_ascii=False, indent=2)
        )

    full_prompt = (
        f"{RULE_MEDICAL_SYSTEM_PROMPT}\n\n"
        f"## Thông tin bệnh nhân / Câu hỏi:\n{state.get('user_message', '')}"
        f"{image_section}\n\n"
        f"## Tài liệu y tế liên quan (từ cơ sở dữ liệu RAG):\n{chunks_text}\n\n"
        "Dựa trên thông tin trên, phân tích và trả về JSON theo cấu trúc đã định nghĩa:"
    )

    loop = asyncio.get_running_loop()
    try:
        raw_text = await loop.run_in_executor(None, _call_gemini_text, full_prompt)
        result = _extract_json(raw_text)

        diagnosis = result.get("diagnosis", {})
        treatment = result.get("treatment", {})

        # Lưu rag_context (tóm tắt từ AI)
        state["rag_context"] = result.get("rag_context", chunks_text[:2000])

        # Lưu treatment_data tổng hợp để persist_to_db dùng
        state["treatment_data"] = {
            "symptoms": diagnosis.get("symptoms", []),
            "possible_conditions": diagnosis.get("possible_conditions", []),
            "severity": diagnosis.get("severity", "mild"),
            "body_parts": diagnosis.get("body_parts"),
            "recommended_specialty": treatment.get("recommended_specialty"),
            "urgency": treatment.get("urgency", "routine"),
            "immediate_actions": treatment.get("immediate_actions", []),
            "medications_mentioned": treatment.get("medications_mentioned", []),
            "lifestyle_advice": treatment.get("lifestyle_advice", []),
        }

        state["urgency_level"] = treatment.get("urgency", "routine")

        logger.info(
            "RAG analysis OK: conditions=%s, severity=%s, urgency=%s",
            diagnosis.get("possible_conditions", [])[:2],
            diagnosis.get("severity"),
            treatment.get("urgency"),
        )

    except json.JSONDecodeError as exc:
        logger.error("RAG JSON parse lỗi: %s", exc)
        state["rag_context"] = chunks_text[:2000]
        state["treatment_data"] = None
        state["urgency_level"] = "routine"
    except Exception as exc:
        logger.error("Rule medical agent lỗi: %s", exc)
        state["rag_context"] = chunks_text[:2000] if chunks_text else ""
        state["treatment_data"] = None
        state["urgency_level"] = "routine"

    return state
