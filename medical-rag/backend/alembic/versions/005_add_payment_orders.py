# -*- coding: utf-8 -*-
"""add payment_orders table

Revision ID: 005
Revises: 004
Create Date: 2026-05-21 12:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic
revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "payment_orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("order_code", sa.String(length=50), nullable=False),
        sa.Column("package_code", sa.String(length=20), nullable=True),
        sa.Column("amount_vnd", sa.Integer(), nullable=False),
        sa.Column("points_credited", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False,
            server_default="PENDING",
        ),
        sa.Column("payment_method", sa.String(length=20), nullable=True),
        sa.Column(
            "provider", sa.String(length=20), nullable=False,
            server_default="VNPAY",
        ),
        sa.Column("provider_txn_id", sa.String(length=100), nullable=True),
        sa.Column("raw_callback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fail_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_payment_orders_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_orders")),
        sa.UniqueConstraint("order_code", name=op.f("uq_payment_orders_order_code")),
    )
    op.create_index(
        op.f("ix_payment_orders_user_id"), "payment_orders", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_orders_order_code"), "payment_orders", ["order_code"], unique=True
    )
    op.create_index(
        op.f("ix_payment_orders_status"), "payment_orders", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_payment_orders_created_at"), "payment_orders", ["created_at"], unique=False
    )
    op.create_index(
        "ix_payment_orders_user_created", "payment_orders",
        ["user_id", "created_at"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_payment_orders_user_created", table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_created_at"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_status"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_order_code"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_user_id"), table_name="payment_orders")
    op.drop_table("payment_orders")
