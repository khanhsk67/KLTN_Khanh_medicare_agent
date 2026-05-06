# -*- coding: utf-8 -*-
"""Fix image_url column type: VARCHAR(1024) -> Text

Revision ID: 002
Revises: 001
Create Date: 2026-05-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "chat_messages",
        "image_url",
        type_=sa.Text(),
        existing_type=sa.String(1024),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "chat_messages",
        "image_url",
        type_=sa.String(1024),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
