"""add per-agent context compaction token limit

Revision ID: 20260715_0003
Revises: 20260714_0002
Create Date: 2026-07-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260715_0003"
down_revision: Union[str, None] = "20260714_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("context_token_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "context_token_limit")
