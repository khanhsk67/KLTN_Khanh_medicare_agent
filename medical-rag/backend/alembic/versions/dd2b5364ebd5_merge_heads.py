"""merge heads

Revision ID: dd2b5364ebd5
Revises: 002, 15681c5a4c91
Create Date: 2026-05-11 04:53:47.383953+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic
revision: str = 'dd2b5364ebd5'
down_revision: str | None = ('002', '15681c5a4c91')
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
