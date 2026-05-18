# -*- coding: utf-8 -*-
"""
Chat Service — quản lý session, messages và treatment records.
"""
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.chat_message import ChatMessage
from app.db.models.chat_session import ChatSession
from app.db.models.chat_usage import ChatUsage
from app.db.models.treatment_record import TreatmentRecord
from app.services import wallet_service

logger = logging.getLogger(__name__)


async def _save_chat_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    response: Any,
    usage_id: uuid.UUID,
) -> tuple[int, int]:
    """
    Lấy token usage từ OpenAI response,
    tính chi phí, trừ điểm, lưu chat_usages.
    Trả về: (charged_points, balance_remaining)
    """
    # Lấy token từ OpenAI usage
    try:
        input_tokens  = response.usage.prompt_tokens or 0
        output_tokens = response.usage.completion_tokens or 0
    except AttributeError:
        # Fallback nếu OpenAI không trả usage (vd streaming không bật include_usage)
        input_tokens, output_tokens = 0, 0

    # Tính chi phí
    cost_usd, cost_vnd, charged_points = wallet_service.calculate_chat_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    # Lưu chat_usage record
    usage = ChatUsage(
        id=usage_id,
        user_id=user_id,
        session_id=session_id,
        model_name=settings.LLM_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        real_cost_usd=cost_usd,
        real_cost_vnd=cost_vnd,
        charged_points=charged_points,
    )
    db.add(usage)
    await db.flush()

    # Trừ điểm
    wallet = await wallet_service.deduct_points(
        db=db,
        user_id=user_id,
        points=charged_points,
        source="CHAT",
        reference_id=usage_id,
        description=(
            f"Chat: {input_tokens} input + {output_tokens} output tokens"
        ),
    )

    return charged_points, wallet.balance


async def get_or_create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None,
) -> ChatSession:
    """
    Trả về session hiện có (kiểm tra user ownership) hoặc tạo mới nếu không tìm thấy.
    """
    if session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
        )
        session = result.scalar_one_or_none()
        if session:
            return session

    session = ChatSession(user_id=user_id, title="Cuộc tư vấn mới")
    db.add(session)
    await db.flush()
    return session


async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    image_urls: list[str] | None = None,
    image_analysis: list[dict] | None = None,
    sources: Any | None = None,
    urgency: str | None = None,
) -> ChatMessage:
    """Lưu một tin nhắn vào database."""
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        image_urls=image_urls,
        image_analysis=image_analysis,
        sources=sources,
        urgency_level=urgency,
    )
    db.add(msg)
    await db.flush()
    return msg


async def get_session_history(
    db: AsyncSession,
    session_id: uuid.UUID,
    limit: int = 20,
) -> list[ChatMessage]:
    """Lấy lịch sử tin nhắn của session, sắp xếp theo thứ tự thời gian tăng dần."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    # Đảo ngược để có thứ tự thời gian tăng dần
    return list(reversed(messages))


async def update_session_summary(
    db: AsyncSession,
    session_id: uuid.UUID,
    summary: str,
) -> None:
    """Cập nhật tóm tắt của session."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session:
        session.summary = summary
        await db.flush()


async def save_treatment_record(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    agent_result: dict,
) -> TreatmentRecord | None:
    """
    Lưu TreatmentRecord từ kết quả của treatment_analysis_agent.
    Trả về None nếu không có đủ dữ liệu hoặc đã tồn tại record cho session này.
    """
    if not agent_result:
        return None

    symptoms: list = agent_result.get("symptoms", [])
    possible_conditions: list = agent_result.get("possible_conditions", [])
    if not symptoms and not possible_conditions:
        return None

    # Tránh tạo record trùng cho cùng một session
    existing = await db.execute(
        select(TreatmentRecord).where(TreatmentRecord.session_id == session_id)
    )
    if existing.scalar_one_or_none():
        return None

    severity_raw = agent_result.get("severity", "mild")
    severity = severity_raw if severity_raw in ("mild", "moderate", "severe") else "mild"

    record = TreatmentRecord(
        user_id=user_id,
        session_id=session_id,
        symptoms=symptoms,
        possible_conditions=possible_conditions,
        severity=severity,
        body_parts=agent_result.get("body_parts"),
        recommended_specialty=agent_result.get("recommended_specialty"),
        urgency=agent_result.get("urgency", "routine"),
    )
    db.add(record)
    await db.flush()
    return record
