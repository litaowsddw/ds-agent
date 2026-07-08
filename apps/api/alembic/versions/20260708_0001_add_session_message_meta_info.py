"""add session message meta info

Revision ID: 20260708_0001
Revises: 
Create Date: 2026-07-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260708_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "session_messages",
        sa.Column("meta_info", sa.Text(), nullable=True, server_default=sa.text("('{}')")),
    )
    op.execute("UPDATE session_messages SET meta_info = '{}' WHERE meta_info IS NULL")


def downgrade() -> None:
    op.drop_column("session_messages", "meta_info")
