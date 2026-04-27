# -*- coding: utf-8 -*-
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.services import checkin_service

router = APIRouter(prefix="/checkin", tags=["Daily Checkin"])


@router.get("/status")
async def checkin_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Kiểm tra hôm nay đã điểm danh chưa."""
    return await checkin_service.get_checkin_status(db, current_user.id)


@router.post("/daily")
async def daily_checkin(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Điểm danh hằng ngày — nhận 50 điểm.
    409 nếu đã điểm danh hôm nay.
    """
    return await checkin_service.do_daily_checkin(db, current_user.id)
