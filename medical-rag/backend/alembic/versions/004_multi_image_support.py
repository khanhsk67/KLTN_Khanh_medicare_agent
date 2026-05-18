# -*- coding: utf-8 -*-
"""multi-image support + image_analysis cache

- chat_messages.image_url (TEXT)  -> chat_messages.image_urls (JSONB array)
- chat_messages.image_analysis (JSONB, new) -> cache Vision analysis per turn

Backfill: existing image_url non-null wrapped into single-element array.

Revision ID: 004
Revises: d6143a683bbc
Create Date: 2026-05-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: str | None = "d6143a683bbc"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Add new columns
    op.add_column(
        "chat_messages",
        sa.Column("image_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column(
            "image_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    # 2. Backfill image_urls from existing image_url
    op.execute(
        """
        UPDATE chat_messages
        SET image_urls = jsonb_build_array(image_url)
        WHERE image_url IS NOT NULL AND image_url <> ''
        """
    )

    # 3. Drop legacy column
    op.drop_column("chat_messages", "image_url")


def downgrade() -> None:
    # Restore legacy column
    op.add_column(
        "chat_messages",
        sa.Column("image_url", sa.Text(), nullable=True),
    )

    # Backfill: take first element of image_urls array (if any)
    op.execute(
        """
        UPDATE chat_messages
        SET image_url = image_urls->>0
        WHERE image_urls IS NOT NULL AND jsonb_array_length(image_urls) > 0
        """
    )

    op.drop_column("chat_messages", "image_analysis")
    op.drop_column("chat_messages", "image_urls")
