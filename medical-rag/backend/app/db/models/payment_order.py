# -*- coding: utf-8 -*-
"""
PaymentOrder — đơn hàng nạp điểm bằng tiền thật.
Liên kết với VNPay (hoặc cổng khác trong tương lai).
Khi webhook xác nhận PAID → tạo PointTransaction source='PURCHASE'.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Integer, DateTime, ForeignKey, String, Text,
    UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


# Status enum (giữ dưới dạng String để dễ migrate)
ORDER_STATUS_PENDING = "PENDING"
ORDER_STATUS_SUCCESS = "SUCCESS"
ORDER_STATUS_FAILED = "FAILED"
ORDER_STATUS_CANCELLED = "CANCELLED"
ORDER_STATUS_EXPIRED = "EXPIRED"


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Mã đơn gửi cho provider (max 50 chars).
    # VNPay yêu cầu vnp_TxnRef unique, dạng số. Ta dùng timestamp + random.
    order_code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )

    # 'STARTER' | 'BASIC' | 'STANDARD' | 'PRO' | 'PREMIUM' | None (custom)
    package_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    points_credited: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ORDER_STATUS_PENDING,
        index=True,
    )

    # 'VIETQR' | 'CARD' | 'ATM' | 'MOMO' | ...
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # 'VNPAY' (cứng cho phase 1); để mở khi thêm provider khác
    provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default="VNPAY"
    )

    # Mã giao dịch từ provider (vnp_TransactionNo, etc.)
    provider_txn_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Payload webhook gốc — audit + debug
    raw_callback: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Nguyên nhân nếu FAILED / CANCELLED
    fail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_payment_orders_user_created", "user_id", "created_at"),
    )
