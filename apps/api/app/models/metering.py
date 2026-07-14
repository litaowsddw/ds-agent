"""Immutable persistence models for provider-reported LLM usage."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _event_id() -> str:
    return uuid4().hex


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LLMUsageEventModel(Base):
    """One immutable accounting fact for a provider attempt."""

    __tablename__ = "llm_usage_events"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "gateway_call_id", name="uq_llm_usage_events_org_gateway_call"
        ),
        Index("ix_llm_usage_events_org_created_at", "org_id", "created_at"),
        Index(
            "ix_llm_usage_events_org_provider_model_created_at",
            "org_id",
            "provider_key",
            "model",
            "created_at",
        ),
        Index(
            "ix_llm_usage_events_org_agent_created_at", "org_id", "agent_id", "created_at"
        ),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_event_id)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gateway_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    api_name: Mapped[str] = mapped_column(String(128), nullable=False)

    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dispatch_status: Mapped[str] = mapped_column(String(32), nullable=False)
    usage_status: Mapped[str] = mapped_column(String(32), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cache_usage_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    cache_read_input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cache_write_input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    prefix_cache_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prefix_length_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prefix_diagnostic_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    estimated_cost_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    estimated_input_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    estimated_output_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    estimated_cache_read_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    estimated_cache_write_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    estimated_total_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class ModelPriceModel(Base):
    """Versioned per-model prices reserved for optional cost estimation."""

    __tablename__ = "model_prices"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "provider_key",
            "model",
            "effective_at",
            name="uq_model_prices_org_provider_model_effective_at",
        ),
        Index(
            "ix_model_prices_org_provider_model_effective_at",
            "org_id",
            "provider_key",
            "model",
            "effective_at",
        ),
    )

    price_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_event_id)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    input_price_per_million_tokens: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    output_price_per_million_tokens: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    cache_read_price_per_million_tokens: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    cache_write_price_per_million_tokens: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
