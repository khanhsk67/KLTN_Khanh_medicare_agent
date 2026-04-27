# -*- coding: utf-8 -*-
import uuid
from datetime import datetime, timezone, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.models.daily_checkin import DailyCheckin
from app.services import wallet_service


async def get_checkin_status(
    db: AsyncSession,
    user_id: uuid.UUID
) -> dict:
    """Kiểm tra hôm nay user đã điểm danh chưa."""
    today = date.today()
    result = await db.execute(
        select(DailyCheckin).where(
            DailyCheckin.user_id == user_id,
            DailyCheckin.checkin_date == today
        )
    )
    checkin = result.scalar_one_or_none()
    return {
        "checked_today": checkin is not None,
        "reward_points": settings.DAILY_CHECKIN_REWARD,
        "checkin_date": today.isoformat()
    }


async def do_daily_checkin(
    db: AsyncSession,
    user_id: uuid.UUID
) -> dict:
    """
    Thực hiện điểm danh hằng ngày.
    - Mỗi ngày chỉ được 1 lần (UNIQUE constraint đảm bảo)
    - Cộng DAILY_CHECKIN_REWARD điểm vào ví
    """
    today = date.today()

    # Check đã điểm danh hôm nay chưa
    result = await db.execute(
        select(DailyCheckin).where(
            DailyCheckin.user_id == user_id,
            DailyCheckin.checkin_date == today
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bạn đã điểm danh hôm nay rồi. Quay lại vào ngày mai nhé!"
        )

    reward = settings.DAILY_CHECKIN_REWARD

    # Tạo bản ghi checkin
    checkin = DailyCheckin(
        user_id=user_id,
        checkin_date=today,
        reward_points=reward
    )
    db.add(checkin)
    await db.flush()

    # Cộng điểm vào ví
    wallet = await wallet_service.credit_points(
        db=db,
        user_id=user_id,
        points=reward,
        source="DAILY_CHECKIN",
        reference_id=checkin.id,
        description=f"Điểm danh ngày {today.strftime('%d/%m/%Y')}"
    )

    return {
        "success": True,
        "rewarded_points": reward,
        "balance": wallet.balance,
        "already_checked": False,
        "message": f"Điểm danh thành công! +{reward} điểm"
    }
