"""add immutable LLM usage events and model prices

Revision ID: 20260714_0002
Revises: 20260708_0001
Create Date: 2026-07-14 00:02:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0002"
down_revision: Union[str, None] = "20260708_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("gateway_call_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("api_name", sa.String(length=128), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_version_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_node_id", sa.String(length=64), nullable=True),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dispatch_status", sa.String(length=32), nullable=False),
        sa.Column("usage_status", sa.String(length=32), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("total_tokens", sa.BigInteger(), nullable=True),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=True),
        sa.Column("cache_usage_status", sa.String(length=32), nullable=False),
        sa.Column("cache_read_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("cache_write_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("prefix_cache_status", sa.String(length=32), nullable=True),
        sa.Column("prefix_length_bucket", sa.String(length=32), nullable=True),
        sa.Column("prefix_diagnostic_key_id", sa.String(length=64), nullable=True),
        sa.Column("estimated_cost_status", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("estimated_input_cost", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("estimated_output_cost", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("estimated_cache_read_cost", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("estimated_cache_write_cost", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("estimated_total_cost", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_http_status", sa.Integer(), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "org_id", "gateway_call_id", name="uq_llm_usage_events_org_gateway_call"
        ),
    )
    op.create_index(
        "ix_llm_usage_events_org_created_at", "llm_usage_events", ["org_id", "created_at"]
    )
    op.create_index(
        "ix_llm_usage_events_org_provider_model_created_at",
        "llm_usage_events",
        ["org_id", "provider_key", "model", "created_at"],
    )
    op.create_index(
        "ix_llm_usage_events_org_agent_created_at",
        "llm_usage_events",
        ["org_id", "agent_id", "created_at"],
    )
    op.execute(
        """
        CREATE TRIGGER llm_usage_events_no_update
        BEFORE UPDATE ON llm_usage_events
        FOR EACH ROW
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'llm_usage_events are immutable'
        """
    )
    op.create_table(
        "model_prices",
        sa.Column("price_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "input_price_per_million_tokens", sa.Numeric(precision=20, scale=8), nullable=True
        ),
        sa.Column(
            "output_price_per_million_tokens", sa.Numeric(precision=20, scale=8), nullable=True
        ),
        sa.Column(
            "cache_read_price_per_million_tokens",
            sa.Numeric(precision=20, scale=8),
            nullable=True,
        ),
        sa.Column(
            "cache_write_price_per_million_tokens",
            sa.Numeric(precision=20, scale=8),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("price_id"),
        sa.UniqueConstraint(
            "org_id",
            "provider_key",
            "model",
            "effective_at",
            name="uq_model_prices_org_provider_model_effective_at",
        ),
    )
    op.create_index(
        "ix_model_prices_org_provider_model_effective_at",
        "model_prices",
        ["org_id", "provider_key", "model", "effective_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_prices_org_provider_model_effective_at", table_name="model_prices")
    op.drop_table("model_prices")
    op.execute("DROP TRIGGER IF EXISTS llm_usage_events_no_update")
    op.drop_index("ix_llm_usage_events_org_agent_created_at", table_name="llm_usage_events")
    op.drop_index(
        "ix_llm_usage_events_org_provider_model_created_at", table_name="llm_usage_events"
    )
    op.drop_index("ix_llm_usage_events_org_created_at", table_name="llm_usage_events")
    op.drop_table("llm_usage_events")
