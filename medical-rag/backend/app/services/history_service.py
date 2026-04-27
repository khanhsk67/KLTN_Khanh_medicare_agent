# -*- coding: utf-8 -*-
"""
History Service — quản lý lịch sử tư vấn của người dùng.
"""
import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.chat_session import ChatSession
from app.models.schemas import PaginatedSessions, SessionResponse, SessionWithMessages


async def list_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedSessions:
    """Lấy danh sách sessions của user với phân trang."""
    offset = (page - 1) * page_size

    total_result = await db.execute(
        select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    sessions = result.scalars().all()

    pages = math.ceil(total / page_size) if page_size > 0 else 0
    return PaginatedSessions(
        items=[SessionResponse.model_validate(s) for s in sessions],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


async def get_session_detail(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> SessionWithMessages:
    """Lấy chi tiết session kèm tất cả messages. Kiểm tra user ownership."""
    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        .options(selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return SessionWithMessages.model_validate(session)


async def delete_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> None:
    """Xóa session và toàn bộ messages liên quan (cascade). Kiểm tra user ownership."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    await db.delete(session)
    await db.flush()


async def search_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
) -> list[SessionResponse]:
    """Tìm kiếm sessions theo title hoặc summary (case-insensitive)."""
    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.user_id == user_id,
            or_(
                ChatSession.title.ilike(f"%{query}%"),
                ChatSession.summary.ilike(f"%{query}%"),
            ),
        )
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    return [SessionResponse.model_validate(s) for s in sessions]
