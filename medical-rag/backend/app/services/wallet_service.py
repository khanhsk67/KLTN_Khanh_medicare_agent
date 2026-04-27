# -*- coding: utf-8 -*-
"""
Wallet Service — quản lý số dư và biến động điểm.
Mọi thao tác cộng/trừ điểm phải đi qua service này
để đảm bảo audit trail đầy đủ trong point_transactions.
"""
import math
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.models.wallet import Wallet
from app.db.models.point_transaction import PointTransaction


async def get_or_create_wallet(
    db: AsyncSession,
    user_id: uuid.UUID
) -> Wallet:
    """Lấy ví của user, tự tạo nếu chưa có."""
    result = await db.execute(
        select(Wallet).where(Wallet.user_id == user_id)
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.add(wallet)
        await db.flush()  # lấy id ngay mà chưa commit

    return wallet


async def get_balance(
    db: AsyncSession,
    user_id: uuid.UUID
) -> int:
    wallet = await get_or_create_wallet(db, user_id)
    return wallet.balance


async def credit_points(
    db: AsyncSession,
    user_id: uuid.UUID,
    points: int,
    source: str,           # 'DAILY_CHECKIN' | 'PROMO_CODE' | 'ADMIN_BONUS' | 'PURCHASE'
    reference_id: uuid.UUID | None = None,
    description: str | None = None
) -> Wallet:
    """
    Cộng điểm vào ví + ghi point_transaction.
    Dùng cho: điểm danh, promo code, admin thưởng.
    """
    if points <= 0:
        raise ValueError("Số điểm phải lớn hơn 0")

    wallet = await get_or_create_wallet(db, user_id)
    balance_before = wallet.balance
    wallet.balance += points

    tx = PointTransaction(
        user_id=user_id,
        wallet_id=wallet.id,
        type="CREDIT",
        source=source,
        points=points,
        balance_before=balance_before,
        balance_after=wallet.balance,
        reference_id=reference_id,
        description=description or f"Cộng {points} điểm — {source}"
    )
    db.add(tx)
    await db.flush()
    return wallet


async def deduct_points(
    db: AsyncSession,
    user_id: uuid.UUID,
    points: int,
    source: str,           # 'CHAT'
    reference_id: uuid.UUID | None = None,
    description: str | None = None
) -> Wallet:
    """
    Trừ điểm khỏi ví + ghi point_transaction.
    Raise 402 nếu không đủ điểm.
    """
    if points <= 0:
        raise ValueError("Số điểm phải lớn hơn 0")

    wallet = await get_or_create_wallet(db, user_id)

    if wallet.balance < points:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Không đủ điểm. Cần {points} điểm, "
                f"hiện có {wallet.balance} điểm."
            )
        )

    balance_before = wallet.balance
    wallet.balance -= points

    tx = PointTransaction(
        user_id=user_id,
        wallet_id=wallet.id,
        type="DEBIT",
        source=source,
        points=points,
        balance_before=balance_before,
        balance_after=wallet.balance,
        reference_id=reference_id,
        description=description or f"Trừ {points} điểm — {source}"
    )
    db.add(tx)
    await db.flush()
    return wallet


async def check_minimum_balance(
    db: AsyncSession,
    user_id: uuid.UUID
) -> None:
    """
    Kiểm tra user có đủ điểm tối thiểu để chat không.
    Raise 402 nếu không đủ.
    """
    wallet = await get_or_create_wallet(db, user_id)
    if wallet.balance < settings.MIN_POINTS_TO_CHAT:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Cần ít nhất {settings.MIN_POINTS_TO_CHAT} điểm để chat. "
                f"Hãy điểm danh hoặc nhập mã điểm để nhận thêm."
            )
        )


def calculate_chat_cost(
    input_tokens: int,
    output_tokens: int
) -> tuple[float, int, int]:
    """
    Tính chi phí từ token usage Gemini.
    Trả về: (cost_usd, cost_vnd, charged_points)
    """
    cost_usd = (
        input_tokens  * settings.GEMINI_INPUT_PRICE_USD  / 1_000_000 +
        output_tokens * settings.GEMINI_OUTPUT_PRICE_USD / 1_000_000
    )
    cost_vnd       = int(cost_usd * settings.USD_TO_VND_RATE)
    charged_points = math.ceil(cost_vnd / settings.POINT_VALUE_VND)

    # Tối thiểu 1 điểm mỗi lượt chat
    return cost_usd, cost_vnd, max(1, charged_points)


async def get_topup_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 20
) -> list[PointTransaction]:
    """
    Lịch sử nạp điểm — chỉ lấy CREDIT transactions.
    Dùng cho frontend trang Ví điểm.
    """
    result = await db.execute(
        select(PointTransaction)
        .where(
            PointTransaction.user_id == user_id,
            PointTransaction.type == "CREDIT"
        )
        .order_by(PointTransaction.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
