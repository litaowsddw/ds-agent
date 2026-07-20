"""expand workflow run status for explicit approval lifecycle states

Revision ID: 20260720_0007
Revises: 20260720_0006
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_0007"
down_revision = "20260720_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table keeps this migration portable to SQLite development
    # databases while using an in-place ALTER on production engines where it
    # is supported.
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
