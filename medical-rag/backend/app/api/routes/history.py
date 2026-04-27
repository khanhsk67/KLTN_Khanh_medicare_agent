# -*- coding: utf-8 -*-
"""
History Routes — xem và quản lý lịch sử tư vấn.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.models.schemas import PaginatedSessions, SessionResponse, SessionWithMessages
from app.services import history_service

router = APIRouter(prefix="/api/history", tags=["history"])


# ---------------------------------------------------------------------------
# GET /api/history/sessions
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=PaginatedSessions)
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedSessions:
    """Danh sách sessions của user hiện tại, sắp xếp theo thời gian cập nhật mới nhất."""
    return await history_service.list_sessions(db, current_user.id, page, page_size)


# ---------------------------------------------------------------------------
# GET /api/history/sessions/{id}
# ---------------------------------------------------------------------------

@router.get("/sessions/{session_id}", response_model=SessionWithMessages)
async def get_session(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionWithMessages:
    """Chi tiết một session kèm toàn bộ messages."""
    return await history_service.get_session_detail(db, current_user.id, session_id)


# ---------------------------------------------------------------------------
# DELETE /api/history/sessions/{id}
# ---------------------------------------------------------------------------

@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Xóa session và toàn bộ messages liên quan."""
    await history_service.delete_session(db, current_user.id, session_id)


# ---------------------------------------------------------------------------
# GET /api/history/search?q=...
# ---------------------------------------------------------------------------

@router.get("/search", response_model=list[SessionResponse])
async def search_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(..., min_length=1, max_length=200),
) -> list[SessionResponse]:
    """Tìm kiếm sessions theo từ khóa trong title và summary."""
    return await history_service.search_sessions(db, current_user.id, q)
