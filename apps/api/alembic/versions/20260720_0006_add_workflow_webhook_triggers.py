"""add secure webhook triggers for immutable workflow versions

Revision ID: 20260720_0006
Revises: 20260720_0005
Create Date: 2026-07-20 00:06:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_0006"
down_revision: Union[str, None] = "20260720_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_webhook_triggers",
        sa.Column("trigger_id", sa.String(length=64), primary_key=True),
        sa.Column("workflow_id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("disabled_by", sa.String(length=64), nullable=True),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.workflow_id"]),
        sa.ForeignKeyConstraint(["version_id"], ["workflow_versions.version_id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"]),
        sa.UniqueConstraint("version_id", name="uq_workflow_webhook_trigger_version"),
    )
    op.create_index("ix_workflow_webhook_triggers_workflow_id", "workflow_webhook_triggers", ["workflow_id"])
    op.create_index("ix_workflow_webhook_triggers_version_id", "workflow_webhook_triggers", ["version_id"])
    op.create_index("ix_workflow_webhook_triggers_org_id", "workflow_webhook_triggers", ["org_id"])

    op.create_table(
        "workflow_webhook_deliveries",
        sa.Column("delivery_id", sa.String(length=64), primary_key=True),
        sa.Column("trigger_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["trigger_id"], ["workflow_webhook_triggers.trigger_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.run_id"]),
        sa.UniqueConstraint(
            "trigger_id", "idempotency_key_hash", name="uq_workflow_webhook_delivery_key"
        ),
    )
    op.create_index("ix_workflow_webhook_deliveries_trigger_id", "workflow_webhook_deliveries", ["trigger_id"])
    op.create_index("ix_workflow_webhook_deliveries_run_id", "workflow_webhook_deliveries", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_webhook_deliveries_run_id", table_name="workflow_webhook_deliveries")
    op.drop_index("ix_workflow_webhook_deliveries_trigger_id", table_name="workflow_webhook_deliveries")
    op.drop_table("workflow_webhook_deliveries")
    op.drop_index("ix_workflow_webhook_triggers_org_id", table_name="workflow_webhook_triggers")
    op.drop_index("ix_workflow_webhook_triggers_version_id", table_name="workflow_webhook_triggers")
    op.drop_index("ix_workflow_webhook_triggers_workflow_id", table_name="workflow_webhook_triggers")
    op.drop_table("workflow_webhook_triggers")
