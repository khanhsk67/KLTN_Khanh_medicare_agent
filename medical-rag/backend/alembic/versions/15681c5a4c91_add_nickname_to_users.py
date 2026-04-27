"""add_nickname_to_users

Revision ID: 15681c5a4c91
Revises: 6b650802f8b4
Create Date: 2026-04-27 05:21:41.276134+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = '15681c5a4c91'
down_revision: str | None = '6b650802f8b4'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('nickname', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'nickname')
