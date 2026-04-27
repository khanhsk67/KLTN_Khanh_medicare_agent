# -*- coding: utf-8 -*-
"""
Analysis Service — thống kê và phân tích lịch sử y tế của người dùng.
"""
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat_message import ChatMessage
from app.db.models.chat_session import ChatSession
from app.db.models.treatment_record import TreatmentRecord
from app.models.schemas import (
    AnalysisResponse,
    ConsultationFrequency,
    DetailedStats,
    HealthDashboard,
    HealthTimelineItem,
    SeverityDistribution,
    TimelineEvent,
    TopSymptom,
)


async def get_user_analysis(
    db: AsyncSession,
    user_id: uuid.UUID,
    period_days: int,
) -> AnalysisResponse | None:
    """
    Trả về bản ghi phân tích y tế mới nhất trong khoảng thời gian period_days.
    Trả về None nếu không có dữ liệu.
    """
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    result = await db.execute(
        select(TreatmentRecord)
        .where(
            TreatmentRecord.user_id == user_id,
            TreatmentRecord.created_at >= since,
        )
        .order_by(TreatmentRecord.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        return None
    return AnalysisResponse.model_validate(record)


async def get_health_timeline(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[TimelineEvent]:
    """
    Trả về timeline tổng hợp số session và message theo từng ngày (toàn bộ lịch sử).
    """
    # Sessions per day
    session_result = await db.execute(
        select(
            func.date(ChatSession.created_at).label("d"),
            func.count(ChatSession.id).label("c"),
        )
        .where(ChatSession.user_id == user_id)
        .group_by(func.date(ChatSession.created_at))
        .order_by(func.date(ChatSession.created_at))
    )
    session_rows = session_result.all()

    # Messages per day (thông qua session join)
    msg_result = await db.execute(
        select(
            func.date(ChatMessage.created_at).label("d"),
            func.count(ChatMessage.id).label("c"),
        )
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == user_id)
        .group_by(func.date(ChatMessage.created_at))
    )
    msg_counts: dict[date, int] = {row.d: row.c for row in msg_result.all()}

    return [
        TimelineEvent(
            date=row.d,
            session_count=row.c,
            message_count=msg_counts.get(row.d, 0),
        )
        for row in session_rows
    ]


async def get_statistics(
    db: AsyncSession,
    user_id: uuid.UUID,
    period_days: int,
) -> DetailedStats:
    """
    Thống kê chi tiết trong khoảng period_days ngày:
    - Số sessions, messages, treatment records
    - Phân phối severity và urgency
    - Top symptoms và conditions
    - Timeline toàn bộ lịch sử
    """
    since = datetime.now(timezone.utc) - timedelta(days=period_days)

    # Tổng số sessions trong kỳ
    session_count_result = await db.execute(
        select(func.count(ChatSession.id)).where(
            ChatSession.user_id == user_id,
            ChatSession.created_at >= since,
        )
    )
    total_sessions: int = session_count_result.scalar_one()

    # Tổng số messages trong kỳ
    msg_count_result = await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(
            ChatSession.user_id == user_id,
            ChatMessage.created_at >= since,
        )
    )
    total_messages: int = msg_count_result.scalar_one()

    # Lấy tất cả TreatmentRecords trong kỳ
    tr_result = await db.execute(
        select(TreatmentRecord).where(
            TreatmentRecord.user_id == user_id,
            TreatmentRecord.created_at >= since,
        )
    )
    records = tr_result.scalars().all()

    severity_distribution: dict[str, int] = {}
    urgency_distribution: dict[str, int] = {}
    all_symptoms: list[str] = []
    all_conditions: list[str] = []

    for record in records:
        sev = record.severity or "mild"
        severity_distribution[sev] = severity_distribution.get(sev, 0) + 1

        urg = record.urgency or "routine"
        urgency_distribution[urg] = urgency_distribution.get(urg, 0) + 1

        all_symptoms.extend(record.symptoms or [])
        all_conditions.extend(record.possible_conditions or [])

    top_symptoms = [s for s, _ in Counter(all_symptoms).most_common(10)]
    top_conditions = [c for c, _ in Counter(all_conditions).most_common(10)]
    timeline = await get_health_timeline(db, user_id)

    return DetailedStats(
        total_sessions=total_sessions,
        total_messages=total_messages,
        total_treatment_records=len(records),
        severity_distribution=severity_distribution,
        urgency_distribution=urgency_distribution,
        top_symptoms=top_symptoms,
        top_conditions=top_conditions,
        timeline=timeline,
    )


async def get_health_timeline_items(
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int,
) -> list[HealthTimelineItem]:
    """
    Trả về danh sách HealthTimelineItem từ TreatmentRecord trong khoảng `days` ngày.
    Mỗi item đại diện cho một phiên tư vấn có kết quả phân tích.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(TreatmentRecord)
        .where(
            TreatmentRecord.user_id == user_id,
            TreatmentRecord.created_at >= since,
        )
        .order_by(TreatmentRecord.record_date.desc())
    )
    records = result.scalars().all()

    items: list[HealthTimelineItem] = []
    for r in records:
        symptoms: list[str] = r.symptoms or []
        main_symptom = symptoms[0] if symptoms else "Không xác định"
        items.append(
            HealthTimelineItem(
                id=r.id,
                date=r.record_date,
                main_symptom=main_symptom,
                specialty=r.recommended_specialty,
                severity=r.severity,
                session_id=r.session_id,
            )
        )
    return items


async def get_dashboard(
    db: AsyncSession,
    user_id: uuid.UUID,
    days: int,
) -> HealthDashboard:
    """
    Dashboard tổng quan sức khỏe trong khoảng `days` ngày:
    - Tổng sessions, messages, avg messages/session
    - Top symptoms (tên + số lần xuất hiện)
    - Phân phối severity
    - Tần suất tư vấn theo ngày
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Tổng sessions
    session_count_result = await db.execute(
        select(func.count(ChatSession.id)).where(
            ChatSession.user_id == user_id,
            ChatSession.created_at >= since,
        )
    )
    total_sessions: int = session_count_result.scalar_one()

    # Tổng messages
    msg_count_result = await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(
            ChatSession.user_id == user_id,
            ChatMessage.created_at >= since,
        )
    )
    total_messages: int = msg_count_result.scalar_one()

    avg = round(total_messages / total_sessions, 2) if total_sessions else 0.0

    # TreatmentRecords trong kỳ
    tr_result = await db.execute(
        select(TreatmentRecord).where(
            TreatmentRecord.user_id == user_id,
            TreatmentRecord.created_at >= since,
        )
    )
    records = tr_result.scalars().all()

    all_symptoms: list[str] = []
    sev_counts: dict[str, int] = {"mild": 0, "moderate": 0, "severe": 0}
    for r in records:
        all_symptoms.extend(r.symptoms or [])
        sev = r.severity or "mild"
        if sev in sev_counts:
            sev_counts[sev] += 1

    symptom_counter = Counter(all_symptoms)
    top_symptoms = [
        TopSymptom(name=name, count=count)
        for name, count in symptom_counter.most_common(10)
    ]

    # Tần suất tư vấn theo ngày
    freq_result = await db.execute(
        select(
            func.date(ChatSession.created_at).label("d"),
            func.count(ChatSession.id).label("c"),
        )
        .where(
            ChatSession.user_id == user_id,
            ChatSession.created_at >= since,
        )
        .group_by(func.date(ChatSession.created_at))
        .order_by(func.date(ChatSession.created_at))
    )
    consultation_frequency = [
        ConsultationFrequency(date=str(row.d), count=row.c)
        for row in freq_result.all()
    ]

    return HealthDashboard(
        period_days=days,
        total_sessions=total_sessions,
        total_messages=total_messages,
        avg_messages_per_session=avg,
        top_symptoms=top_symptoms,
        severity_distribution=SeverityDistribution(**sev_counts),
        consultation_frequency=consultation_frequency,
    )
