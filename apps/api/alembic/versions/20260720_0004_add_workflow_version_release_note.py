"""add immutable workflow version release notes

Revision ID: 20260720_0004
Revises: 20260715_0003
Create Date: 2026-07-20 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_0004"
down_revision: Union[str, None] = "20260715_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_versions",
        sa.Column("release_note", sa.String(length=500), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("workflow_versions", "release_note")
