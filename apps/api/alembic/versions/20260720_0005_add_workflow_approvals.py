"""add persistent workflow MCP approval requests

Revision ID: 20260720_0005
Revises: 20260720_0004
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_0005"
down_revision = "20260720_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_approval_requests",
        sa.Column("approval_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("tool_id", sa.String(length=64), nullable=False),
        sa.Column("server_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("arguments_redacted", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("arguments_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("execution_node_run_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.run_id"]),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index("ix_workflow_approval_requests_run_id", "workflow_approval_requests", ["run_id"])
    op.create_index("ix_workflow_approval_requests_org_id", "workflow_approval_requests", ["org_id"])
    op.create_index("ix_workflow_approval_requests_status", "workflow_approval_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_workflow_approval_requests_status", table_name="workflow_approval_requests")
    op.drop_index("ix_workflow_approval_requests_org_id", table_name="workflow_approval_requests")
    op.drop_index("ix_workflow_approval_requests_run_id", table_name="workflow_approval_requests")
    op.drop_table("workflow_approval_requests")
