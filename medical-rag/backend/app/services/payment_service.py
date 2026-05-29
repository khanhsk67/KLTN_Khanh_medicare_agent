# -*- coding: utf-8 -*-
"""
Payment Service — quản lý đơn nạp điểm bằng tiền thật.

Phase 1: chỉ business logic + DB. Không gọi VNPay (phase 2).
Không expose endpoint (phase 3).

Flow:
  create_order() → PENDING
        ↓ (user thanh toán → webhook gọi mark_paid)
  mark_paid()   → SUCCESS + credit_points(source='PURCHASE')
        ↓ hoặc
  mark_failed() / cancel_order() / mark_expired_orders()
"""
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.payment_order import (
    PaymentOrder,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
)
from app.services import wallet_service


# ===================================================================
# PACKAGES — định nghĩa 5 gói nạp cố định
# Bonus tăng theo mức tiền để khuyến khích nạp lớn
# ===================================================================
PACKAGES: list[dict[str, Any]] = [
    {
        "code": "STARTER",
        "label": "Starter",
        "amount_vnd": 10_000,
        "base_points": 100,
        "bonus_points": 0,
        "bonus_percent": 0,
    },
    {
        "code": "BASIC",
        "label": "Basic",
        "amount_vnd": 50_000,
        "base_points": 500,
        "bonus_points": 25,
        "bonus_percent": 5,
    },
    {
        "code": "STANDARD",
        "label": "Standard",
        "amount_vnd": 100_000,
        "base_points": 1_000,
        "bonus_points": 100,
        "bonus_percent": 10,
        "highlight": True,  # gói "HOT" hiển thị nổi bật trên UI
    },
    {
        "code": "PRO",
        "label": "Pro",
        "amount_vnd": 200_000,
        "base_points": 2_000,
        "bonus_points": 300,
        "bonus_percent": 15,
    },
    {
        "code": "PREMIUM",
        "label": "Premium",
        "amount_vnd": 500_000,
        "base_points": 5_000,
        "bonus_points": 1_000,
        "bonus_percent": 20,
    },
]


def get_packages() -> list[dict[str, Any]]:
    """Trả về danh sách gói nạp (kèm tổng điểm sau bonus)."""
    return [
        {
            **pkg,
            "total_points": pkg["base_points"] + pkg["bonus_points"],
        }
        for pkg in PACKAGES
    ]


def get_package(code: str) -> dict[str, Any] | None:
    """Tìm gói theo code, None nếu không tồn tại."""
    for pkg in PACKAGES:
        if pkg["code"] == code:
            return {
                **pkg,
                "total_points": pkg["base_points"] + pkg["bonus_points"],
            }
    return None


def calculate_points_for_amount(
    amount_vnd: int,
    package_code: str | None = None,
) -> int:
    """
    Tính số điểm sẽ được cộng cho 1 amount cho trước.
    - Nếu có package_code → dùng total_points của gói (đã có bonus)
    - Nếu custom amount → chỉ quy đổi 1 điểm = POINT_VALUE_VND, KHÔNG bonus
    """
    if package_code:
        pkg = get_package(package_code)
        if pkg is None:
            raise ValueError(f"Gói '{package_code}' không tồn tại")
        if pkg["amount_vnd"] != amount_vnd:
            raise ValueError(
                f"Số tiền không khớp với gói {package_code}: "
                f"expected {pkg['amount_vnd']}, got {amount_vnd}"
            )
        return pkg["total_points"]

    # Custom amount — không bonus
    if amount_vnd < settings.PAYMENT_MIN_CUSTOM_AMOUNT:
        raise ValueError(
            f"Số tiền tối thiểu là {settings.PAYMENT_MIN_CUSTOM_AMOUNT:,}đ"
        )
    if amount_vnd % settings.POINT_VALUE_VND != 0:
        raise ValueError(
            f"Số tiền phải chia hết cho {settings.POINT_VALUE_VND}đ"
        )
    return amount_vnd // settings.POINT_VALUE_VND


def _generate_order_code() -> str:
    """
    Sinh mã đơn unique cho VNPay (vnp_TxnRef).
    Format: YYYYMMDDHHMMSS + 6 chữ số random.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand = random.randint(100_000, 999_999)
    return f"{ts}{rand}"


# ===================================================================
# CREATE ORDER
# ===================================================================
async def create_order(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    package_code: str | None = None,
    custom_amount_vnd: int | None = None,
    payment_method: str = "VIETQR",
    provider: str = "VNPAY",
) -> PaymentOrder:
    """
    Tạo đơn nạp PENDING.
    Phải truyền 1 trong 2: package_code hoặc custom_amount_vnd.
    """
    # Validate input
    if package_code and custom_amount_vnd:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Chỉ được chọn 1 trong package_code hoặc custom_amount_vnd",
        )
    if not package_code and not custom_amount_vnd:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Phải chọn package_code hoặc nhập custom_amount_vnd",
        )

    if package_code:
        pkg = get_package(package_code)
        if pkg is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Gói '{package_code}' không tồn tại",
            )
        amount_vnd = pkg["amount_vnd"]
        points = pkg["total_points"]
    else:
        amount_vnd = custom_amount_vnd  # type: ignore[assignment]
        try:
            points = calculate_points_for_amount(amount_vnd)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    now = datetime.now(timezone.utc)
    expired_at = now + timedelta(minutes=settings.PAYMENT_ORDER_EXPIRE_MINUTES)

    order = PaymentOrder(
        user_id=user_id,
        order_code=_generate_order_code(),
        package_code=package_code,
        amount_vnd=amount_vnd,
        points_credited=points,
        status=ORDER_STATUS_PENDING,
        payment_method=payment_method,
        provider=provider,
        created_at=now,
        expired_at=expired_at,
    )
    db.add(order)
    await db.flush()
    return order


# ===================================================================
# MARK PAID — idempotent, an toàn khi webhook gọi 2 lần
# ===================================================================
async def mark_paid(
    db: AsyncSession,
    order_code: str,
    *,
    provider_txn_id: str,
    raw_callback: dict[str, Any] | None = None,
    amount_vnd: int | None = None,
) -> PaymentOrder:
    """
    Đánh dấu đơn SUCCESS + cộng điểm cho user.

    Idempotent: nếu order đã SUCCESS thì return luôn, không cộng điểm lần 2.

    Kiểm tra amount_vnd (nếu có) khớp với DB để chống giả mạo callback.

    Raise:
      404 nếu order không tồn tại
      409 nếu order đã FAILED/CANCELLED/EXPIRED
      400 nếu amount mismatch
    """
    # Lock row để tránh race condition khi webhook gọi đồng thời
    result = await db.execute(
        select(PaymentOrder)
        .where(PaymentOrder.order_code == order_code)
        .with_for_update()
    )
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Đơn '{order_code}' không tồn tại",
        )

    # Idempotency check — đã SUCCESS từ trước
    if order.status == ORDER_STATUS_SUCCESS:
        return order

    # Đơn đã ở trạng thái không thể chuyển sang SUCCESS
    if order.status in (
        ORDER_STATUS_FAILED, ORDER_STATUS_CANCELLED, ORDER_STATUS_EXPIRED
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đơn '{order_code}' đã ở trạng thái {order.status}, không thể chuyển sang SUCCESS",
        )

    # Verify amount nếu provider gửi kèm
    if amount_vnd is not None and amount_vnd != order.amount_vnd:
        # Flag FAILED để admin biết có vấn đề
        order.status = ORDER_STATUS_FAILED
        order.fail_reason = (
            f"Amount mismatch: order={order.amount_vnd}, callback={amount_vnd}"
        )
        order.raw_callback = raw_callback
        await db.flush()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Số tiền callback không khớp với đơn",
        )

    # OK — cộng điểm
    await wallet_service.credit_points(
        db,
        user_id=order.user_id,
        points=order.points_credited,
        source="PURCHASE",
        reference_id=order.id,
        description=(
            f"Nạp {order.amount_vnd:,}đ → +{order.points_credited} điểm "
            f"(đơn {order.order_code})"
        ),
    )

    order.status = ORDER_STATUS_SUCCESS
    order.provider_txn_id = provider_txn_id
    order.raw_callback = raw_callback
    order.paid_at = datetime.now(timezone.utc)
    await db.flush()
    return order


# ===================================================================
# MARK FAILED / CANCEL / EXPIRE
# ===================================================================
async def mark_failed(
    db: AsyncSession,
    order_code: str,
    *,
    reason: str,
    raw_callback: dict[str, Any] | None = None,
) -> PaymentOrder:
    """Đánh dấu đơn FAILED. Idempotent."""
    result = await db.execute(
        select(PaymentOrder)
        .where(PaymentOrder.order_code == order_code)
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Đơn không tồn tại")

    if order.status == ORDER_STATUS_SUCCESS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Đơn đã SUCCESS, không thể đánh dấu FAILED",
        )
    if order.status in (
        ORDER_STATUS_FAILED, ORDER_STATUS_CANCELLED, ORDER_STATUS_EXPIRED
    ):
        return order  # đã ở trạng thái kết thúc

    order.status = ORDER_STATUS_FAILED
    order.fail_reason = reason
    order.raw_callback = raw_callback
    await db.flush()
    return order


async def cancel_order(
    db: AsyncSession,
    user_id: uuid.UUID,
    order_code: str,
) -> PaymentOrder:
    """
    User chủ động huỷ đơn (chỉ khi PENDING).
    Bảo vệ ownership: user chỉ huỷ được đơn của chính mình.
    """
    result = await db.execute(
        select(PaymentOrder)
        .where(
            PaymentOrder.order_code == order_code,
            PaymentOrder.user_id == user_id,
        )
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Đơn không tồn tại")

    if order.status != ORDER_STATUS_PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Chỉ huỷ được đơn ở trạng thái PENDING (hiện tại: {order.status})",
        )

    order.status = ORDER_STATUS_CANCELLED
    order.fail_reason = "User cancelled"
    await db.flush()
    return order


async def mark_expired_orders(db: AsyncSession) -> int:
    """
    Đánh dấu tất cả đơn PENDING quá hạn → EXPIRED.
    Chạy định kỳ qua background task / cron.
    Trả về số đơn đã expire.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        update(PaymentOrder)
        .where(
            PaymentOrder.status == ORDER_STATUS_PENDING,
            PaymentOrder.expired_at < now,
        )
        .values(status=ORDER_STATUS_EXPIRED, fail_reason="Order expired")
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


# ===================================================================
# QUERIES — for API
# ===================================================================
async def get_order_by_code(
    db: AsyncSession,
    order_code: str,
    user_id: uuid.UUID | None = None,
) -> PaymentOrder | None:
    """
    Lấy 1 đơn theo order_code.
    Nếu truyền user_id → enforce ownership (cho frontend polling).
    """
    stmt = select(PaymentOrder).where(PaymentOrder.order_code == order_code)
    if user_id is not None:
        stmt = stmt.where(PaymentOrder.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_orders(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 20,
) -> list[PaymentOrder]:
    """Lịch sử đơn nạp của user, mới nhất trước."""
    result = await db.execute(
        select(PaymentOrder)
        .where(PaymentOrder.user_id == user_id)
        .order_by(PaymentOrder.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
