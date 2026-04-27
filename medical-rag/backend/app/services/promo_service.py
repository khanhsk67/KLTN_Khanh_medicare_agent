# -*- coding: utf-8 -*-
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.db.models.promo_code import PromoCode, PromoCodeRedemption
from app.services import wallet_service


async def redeem_promo_code(
    db: AsyncSession,
    user_id: uuid.UUID,
    code: str
) -> dict:
    """
    Đổi mã promo lấy điểm.
    Kiểm tra: tồn tại → còn hạn → còn lượt → chưa dùng → cộng điểm
    """
    # 1. Tìm mã
    result = await db.execute(
        select(PromoCode).where(
            PromoCode.code == code.upper().strip(),
            PromoCode.is_active == True
        )
    )
    promo = result.scalar_one_or_none()

    if not promo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mã điểm không tồn tại hoặc đã bị vô hiệu hóa"
        )

    # 2. Kiểm tra hết hạn
    if promo.expired_at and promo.expired_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Mã điểm đã hết hạn sử dụng"
        )

    # 3. Kiểm tra còn lượt dùng
    if promo.used_count >= promo.max_usage:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Mã điểm đã đạt giới hạn sử dụng"
        )

    # 4. Kiểm tra user đã dùng mã này chưa
    used = await db.execute(
        select(PromoCodeRedemption).where(
            PromoCodeRedemption.promo_code_id == promo.id,
            PromoCodeRedemption.user_id == user_id
        )
    )
    if used.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bạn đã sử dụng mã điểm này rồi"
        )

    # 5. Ghi redemption + tăng used_count
    redemption = PromoCodeRedemption(
        promo_code_id=promo.id,
        user_id=user_id,
        points_received=promo.points
    )
    db.add(redemption)
    promo.used_count += 1
    await db.flush()

    # 6. Cộng điểm
    wallet = await wallet_service.credit_points(
        db=db,
        user_id=user_id,
        points=promo.points,
        source="PROMO_CODE",
        reference_id=redemption.id,
        description=f"Mã điểm: {promo.code}"
    )

    return {
        "success": True,
        "code": promo.code,
        "points_received": promo.points,
        "balance": wallet.balance,
        "message": f"Đổi mã thành công! +{promo.points} điểm"
    }


async def seed_promo_codes(db: AsyncSession) -> None:
    """
    Seed promo codes mặc định cho demo/khóa luận.
    Chỉ insert nếu chưa tồn tại.
    """
    from datetime import date
    codes = [
        {"code": "THESIS2026",  "points": 200, "max_usage": 999},
        {"code": "WELCOME100",  "points": 100, "max_usage": 999},
        {"code": "HDCHAM500",   "points": 500, "max_usage": 10},
        {"code": "TESTDEMO",    "points": 300, "max_usage": 50},
    ]
    for c in codes:
        exists = await db.execute(
            select(PromoCode).where(PromoCode.code == c["code"])
        )
        if not exists.scalar_one_or_none():
            db.add(PromoCode(**c))
    await db.commit()
