# -*- coding: utf-8 -*-
"""
Treatment Analysis Agent — phân tích xu hướng sức khỏe từ lịch sử TreatmentRecord.

Không phải LangGraph node — gọi trực tiếp từ analysis route.
"""
import asyncio
import json
import logging
import re
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import google.generativeai as genai
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.prompts import TREATMENT_ANALYSIS_PROMPT
from app.db.models.treatment_record import TreatmentRecord

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GOOGLE_API_KEY)

MIN_RECORDS = 3  # Tối thiểu để phân tích xu hướng có ý nghĩa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str) -> str:
    model = genai.GenerativeModel(settings.LLM_MODEL)
    response = model.generate_content(prompt)
    return response.text


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def _fallback_analysis(stats: dict[str, Any]) -> dict[str, Any]:
    """Trả về analysis tối giản khi Gemini gặp lỗi."""
    severity = stats.get("severity_distribution", {})
    return {
        "health_trend": "stable",
        "trend_summary": (
            f"Phân tích dựa trên {stats['total_records']} hồ sơ trong "
            f"{stats['period_days']} ngày. Hệ thống không thể phân tích chi tiết do lỗi kỹ thuật."
        ),
        "recurring_symptoms": stats.get("top_symptoms", [])[:3],
        "recurring_conditions": stats.get("top_conditions", [])[:3],
        "risk_factors": [],
        "health_insights": [],
        "recommendations": {
            "immediate": [],
            "short_term": ["Tiếp tục theo dõi sức khỏe định kỳ"],
            "long_term": ["Duy trì lối sống lành mạnh"],
        },
        "specialist_consultations": [],
        "severity_trend": {
            "mild_count": severity.get("mild", 0),
            "moderate_count": severity.get("moderate", 0),
            "severe_count": severity.get("severe", 0),
            "trend_direction": "stable",
        },
        "positive_observations": [],
    }


def _compute_stats(
    records: list[TreatmentRecord],
    period_days: int,
) -> dict[str, Any]:
    """Tính thống kê từ danh sách TreatmentRecord."""
    severity_dist: dict[str, int] = {"mild": 0, "moderate": 0, "severe": 0}
    urgency_dist: dict[str, int] = {}
    all_symptoms: list[str] = []
    all_conditions: list[str] = []
    records_summary: list[dict[str, Any]] = []

    for rec in records:
        severity_dist[rec.severity] = severity_dist.get(rec.severity, 0) + 1
        urgency_dist[rec.urgency] = urgency_dist.get(rec.urgency, 0) + 1
        all_symptoms.extend(rec.symptoms or [])
        all_conditions.extend(rec.possible_conditions or [])
        records_summary.append(
            {
                "date": rec.record_date.isoformat(),
                "symptoms": rec.symptoms or [],
                "conditions": rec.possible_conditions or [],
                "severity": rec.severity,
                "urgency": rec.urgency,
                "specialty": rec.recommended_specialty,
                "body_parts": rec.body_parts or [],
            }
        )

    top_symptoms = [s for s, _ in Counter(all_symptoms).most_common(10)]
    top_conditions = [c for c, _ in Counter(all_conditions).most_common(10)]

    return {
        "period_days": period_days,
        "total_records": len(records),
        "date_range": {
            "from": records[0].record_date.isoformat() if records else None,
            "to": records[-1].record_date.isoformat() if records else None,
        },
        "severity_distribution": severity_dist,
        "urgency_distribution": urgency_dist,
        "top_symptoms": top_symptoms,
        "top_conditions": top_conditions,
        "records": records_summary,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def analyze_treatment_history(
    user_id: uuid.UUID,
    period_days: int,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Phân tích xu hướng sức khỏe của user trong period_days ngày gần nhất.

    Args:
        user_id:     UUID của user (đã xác thực)
        period_days: Số ngày nhìn lại (ví dụ: 30, 90, 180)
        db:          AsyncSession

    Returns:
        dict với 2 key:
          - "stats":    thống kê thô (severity_distribution, top_symptoms, ...)
          - "analysis": kết quả AI (health_trend, recommendations, ...)

    Raises:
        ValueError: nếu không đủ MIN_RECORDS hồ sơ
    """
    cutoff: date = date.today() - timedelta(days=period_days)

    result = await db.execute(
        select(TreatmentRecord)
        .where(
            TreatmentRecord.user_id == user_id,
            TreatmentRecord.record_date >= cutoff,
        )
        .order_by(TreatmentRecord.record_date.asc())
    )
    records: list[TreatmentRecord] = list(result.scalars().all())

    if len(records) < MIN_RECORDS:
        raise ValueError(
            f"Cần ít nhất {MIN_RECORDS} hồ sơ khám bệnh để phân tích xu hướng. "
            f"Hiện tại có {len(records)} hồ sơ trong {period_days} ngày qua."
        )

    stats = _compute_stats(records, period_days)

    prompt = (
        f"{TREATMENT_ANALYSIS_PROMPT}\n\n"
        f"## Dữ liệu lịch sử sức khỏe ({period_days} ngày gần nhất):\n"
        + json.dumps(stats, ensure_ascii=False, indent=2)
        + "\n\nPhân tích và trả về JSON theo cấu trúc đã định nghĩa:"
    )

    loop = asyncio.get_running_loop()
    try:
        raw_text = await loop.run_in_executor(None, _call_gemini, prompt)
        analysis = _extract_json(raw_text)
        logger.info(
            "Treatment analysis OK: trend=%s, records=%d",
            analysis.get("health_trend"),
            len(records),
        )
    except json.JSONDecodeError as exc:
        logger.error("Treatment analysis JSON parse lỗi: %s", exc)
        analysis = _fallback_analysis(stats)
    except Exception as exc:
        logger.error("Treatment analysis lỗi: %s", exc)
        analysis = _fallback_analysis(stats)

    return {
        "stats": stats,
        "analysis": analysis,
    }
