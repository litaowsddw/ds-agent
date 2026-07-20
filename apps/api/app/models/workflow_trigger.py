"""Durable, secret-protected webhook triggers for published Workflow versions."""

from __future__ import annotations

from datetime import datetime

from app.database import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class WorkflowWebhookTriggerModel(Base):
    """One externally callable trigger bound to one immutable version snapshot.

    The raw secret is deliberately never a model field.  Only its SHA-256
    verifier is stored, and it is returned exactly once at creation time.
    """

    __tablename__ = "workflow_webhook_triggers"
    __table_args__ = (
        UniqueConstraint("version_id", name="uq_workflow_webhook_trigger_version"),
    )

    trigger_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflows.workflow_id"), nullable=False, index=True
    )
    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_versions.version_id"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.org_id"), nullable=False, index=True
    )
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    disabled_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkflowWebhookDeliveryModel(Base):
    """Idempotency receipt for a webhook delivery.

    Keys are hashed before persistence.  A unique trigger/key pair turns retry
    delivery into a stable run-id response without retaining the caller's key.
    """

    __tablename__ = "workflow_webhook_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "trigger_id", "idempotency_key_hash", name="uq_workflow_webhook_delivery_key"
        ),
    )

    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trigger_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_webhook_triggers.trigger_id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.run_id"), nullable=False, index=True
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
