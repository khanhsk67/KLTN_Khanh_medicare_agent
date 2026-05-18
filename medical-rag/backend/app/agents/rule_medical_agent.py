# -*- coding: utf-8 -*-
"""
Rule Medical Agent — tìm kiếm tài liệu y tế (RAG) và phân tích với OpenAI.
"""
import asyncio
import json
import logging
import re
import time
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.core.prompts import RULE_MEDICAL_SYSTEM_PROMPT
from app.models.schemas import AgentState, SourceChunk
from app.services.vector_store import qdrant_service

logger = logging.getLogger(__name__)

_openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_retry_delay(exc: Exception, default: int = 65) -> int:
    """Lấy retry delay từ thông báo lỗi 429, fallback về default."""
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", str(exc))
    return int(match.group(1)) + 5 if match else default


def _call_openai_text(prompt: str, max_retries: int = 2) -> str:
    """Gọi OpenAI chat completion với auto-retry khi gặp 429."""
    for attempt in range(max_retries + 1):
        try:
            response = _openai_client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
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


def _norm_item(s: str) -> str:
    """Chuẩn hoá 1 finding/condition/body_part: lowercase + strip + collapse spaces."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _build_search_queries(state: AgentState) -> list[str]:
    """
    Build danh sách query cho Qdrant — 1 query / ảnh khi có multi-image,
    fallback về 1 query duy nhất (user_message) khi không có ảnh.

    Mỗi query / ảnh = user_message + findings/conditions/body_parts CỦA RIÊNG ảnh đó.
    Findings/conditions/body_parts được SORT CANONICAL (sau khi normalize) để
    2 ảnh cùng nội dung khác thứ tự cũng sinh ra cùng 1 query → dedupe được.
    """
    user_msg = state.get("user_message", "").strip()

    image_result = state.get("image_analysis_result")
    results_list: list[dict] = []
    if isinstance(image_result, list):
        results_list = [r for r in image_result if isinstance(r, dict)]
    elif isinstance(image_result, dict):
        results_list = [image_result]

    # Không có ảnh → chỉ dùng user_message
    if not results_list:
        return [user_msg] if user_msg else []

    queries: list[str] = []
    for r in results_list:
        parts: list[str] = []
        if user_msg:
            parts.append(user_msg)
        # Canonical form: dedupe + sort để 2 ảnh giống nhau (kể cả khác thứ tự findings)
        # ra cùng 1 query string → dedupe bằng text-level so sánh sau đây.
        findings = sorted(set(_norm_item(f) for f in (r.get("findings") or []) if f))[:3]
        conditions = sorted(set(_norm_item(c) for c in (r.get("suspected_conditions") or []) if c))[:2]
        body_parts = sorted(set(_norm_item(b) for b in (r.get("affected_body_parts") or []) if b))[:2]
        if findings:
            parts.append("Phát hiện: " + ", ".join(findings))
        if conditions:
            parts.append("Nghi ngờ: " + ", ".join(conditions))
        if body_parts:
            parts.append("Vị trí: " + ", ".join(body_parts))
        q = " | ".join(parts) if parts else user_msg
        if q:
            queries.append(q)

    return queries or ([user_msg] if user_msg else [])


def _dedupe_queries(queries: list[str]) -> list[str]:
    """Dedupe theo string exact (sau khi đã canonical hoá ở _build_search_queries)."""
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
    return out


def _chunk_fingerprint(chunk: SourceChunk) -> str:
    """Định danh chunk để dedupe — ưu tiên chunk_id, fallback file+page+content prefix."""
    if chunk.chunk_id:
        return chunk.chunk_id
    return f"{chunk.source_file}#{chunk.page_number}#{(chunk.content or '')[:80]}"


def _merge_chunks_round_robin(
    per_query_chunks: list[list[SourceChunk]], target: int
) -> list[SourceChunk]:
    """
    Round-robin merge từ N list chunks (đã sort theo score) → list duy nhất ≤ target.

    Vòng 0: lấy chunk top từ MỖI ảnh (đảm bảo fair coverage).
    Vòng 1: lấy chunk thứ 2 từ mỗi ảnh.
    ... Dừng khi đủ target hoặc cạn chunks.

    Dedupe theo fingerprint — chunk trùng (xuất hiện trong nhiều query) chỉ giữ 1 lần,
    nhường slot cho chunk khác.
    """
    seen: set[str] = set()
    result: list[SourceChunk] = []

    # Số vòng tối đa = chiều dài list dài nhất
    max_rounds = max((len(lst) for lst in per_query_chunks), default=0)

    for round_idx in range(max_rounds):
        for img_chunks in per_query_chunks:
            if round_idx >= len(img_chunks):
                continue
            chunk = img_chunks[round_idx]
            fp = _chunk_fingerprint(chunk)
            if fp in seen:
                continue
            seen.add(fp)
            result.append(chunk)
            if len(result) >= target:
                return result

    return result


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


def _log_retrieved_chunks(query: str, chunks: list[SourceChunk]) -> None:
    """Log RAG retrieval flow and returned chunks for debugging."""
    logger.info("[RAG] Query sent to vector DB: %s", query[:200])
    logger.info("[RAG] Returned chunks: %d", len(chunks))

    if not chunks:
        logger.warning(
            "[RAG] No chunks returned. Qdrant may be empty or no result passed the score threshold."
        )
        return

    for index, chunk in enumerate(chunks, 1):
        preview = " ".join(chunk.content.split())[:300]
        logger.info(
            "[RAG] Chunk %d/%d | id=%s | score=%s | file=%s | page=%s | preview=%s",
            index,
            len(chunks),
            chunk.chunk_id,
            chunk.relevance_score,
            chunk.source_file,
            chunk.page_number,
            preview,
        )


# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------

async def retrieve_medical_rules(state: AgentState) -> AgentState:
    """
    LangGraph node: RAG search + OpenAI analysis.

    Multi-image strategy:
    1. Build N query (1 / ảnh) hoặc 1 query (text-only)
    2. Search Qdrant song song với top_k cao hơn / query (3 mỗi query)
    3. Merge round-robin + dedupe → giữ top-5 cuối (fair coverage mỗi ảnh)
    4. Gọi OpenAI với chunks + RULE_MEDICAL_SYSTEM_PROMPT
    5. Parse JSON → set state["rag_context"], ["treatment_data"], ["urgency_level"]
    """
    raw_queries = _build_search_queries(state)
    if not raw_queries:
        logger.warning("[RAG] Không có query nào để search — skip RAG")
        state["retrieved_chunks"] = []
        state["sources"] = []
        state["insufficient_context"] = True
        state["rag_context"] = ""
        state["treatment_data"] = None
        state["urgency_level"] = None
        return state

    # Dedupe: 2+ ảnh cùng triệu chứng → 1 query duy nhất (tiết kiệm Qdrant call)
    queries = _dedupe_queries(raw_queries)
    n_dedupes = len(raw_queries) - len(queries)
    if n_dedupes > 0:
        logger.info(
            "[RAG] Dedupe queries: %d query trùng đã gộp (%d raw → %d unique)",
            n_dedupes, len(raw_queries), len(queries),
        )

    # Top-K động theo N query unique:
    # - 1 query → 5 chunks (giữ như cũ)
    # - 2+ query → min(10, 4 + N) — mỗi ảnh có thêm chỗ, cap 10 để không quá tải LLM
    n_unique = len(queries)
    final_target = 5 if n_unique == 1 else min(10, 4 + n_unique)
    # Mỗi query lấy nhiều hơn để có dư cho dedupe + round-robin
    per_query_top_k = max(3, final_target // n_unique + 1)

    logger.info(
        "[RAG] Built %d query unique (multi-image=%s) | per_query_top_k=%d | final_target=%d",
        n_unique, n_unique > 1, per_query_top_k, final_target,
    )
    for i, q in enumerate(queries, start=1):
        logger.info("[RAG] Query #%d: %s", i, q[:150])

    # Resolve collection alias từ state (nếu có) → tên collection thật
    alias = state.get("collection_alias")
    try:
        collection_name = settings.resolve_collection(alias)
    except ValueError as exc:
        logger.error("Collection alias lỗi: %s — fallback về default", exc)
        collection_name = None  # fallback về default

    # Tìm kiếm tài liệu y tế — song song N query
    try:
        logger.info(
            "[RAG] Starting %d parallel vector searches | alias=%s | collection=%s",
            len(queries), alias, collection_name or "default",
        )
        search_results = await asyncio.gather(
            *[
                qdrant_service.search(
                    q, top_k=per_query_top_k, collection_name=collection_name,
                )
                for q in queries
            ],
            return_exceptions=True,
        )
    except Exception as exc:
        logger.error("Qdrant parallel search lỗi: %s", exc)
        search_results = []

    # Lọc exception, log per-query
    per_query_chunks: list[list[SourceChunk]] = []
    for i, r in enumerate(search_results, start=1):
        if isinstance(r, Exception):
            logger.warning("[RAG] Query #%d lỗi: %s — skip", i, r)
            per_query_chunks.append([])
        elif isinstance(r, list):
            logger.info("[RAG] Query #%d → %d chunks raw", i, len(r))
            per_query_chunks.append(r)
        else:
            per_query_chunks.append([])

    # Round-robin merge + dedupe → top-5
    chunks = _merge_chunks_round_robin(per_query_chunks, final_target)

    # Log retrieved chunks final
    _log_retrieved_chunks(" || ".join(queries)[:300], chunks)

    state["retrieved_chunks"] = chunks
    state["sources"] = chunks

    # Không có chunk nào vượt threshold → đánh dấu để chatbot agent trả fallback,
    # và skip luôn phần phân tích Gemini (không có context thì phân tích chỉ tốn quota).
    if not chunks:
        logger.warning(
            "[RAG] Không có chunk nào đạt score_threshold — set insufficient_context=True"
        )
        state["insufficient_context"] = True
        state["rag_context"] = ""
        state["treatment_data"] = None
        state["urgency_level"] = None
        return state

    state["insufficient_context"] = False

    # Format chunks thành context text
    chunks_text = _format_chunks_for_prompt(chunks)

    # Build image analysis section (hỗ trợ list nhiều ảnh)
    image_section = ""
    image_result = state.get("image_analysis_result")
    results_list: list[dict] = []
    if isinstance(image_result, list):
        results_list = [r for r in image_result if isinstance(r, dict)]
    elif isinstance(image_result, dict):
        results_list = [image_result]
    if results_list:
        image_section = (
            "\n\n## Kết quả phân tích hình ảnh y tế ({} ảnh):\n".format(len(results_list))
            + json.dumps(results_list, ensure_ascii=False, indent=2)
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
        raw_text = await loop.run_in_executor(None, _call_openai_text, full_prompt)
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
