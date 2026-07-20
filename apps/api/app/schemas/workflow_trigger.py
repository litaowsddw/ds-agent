"""Contracts for managed Workflow webhook triggers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkflowWebhookTriggerCreateRequest(BaseModel):
    """Create the single webhook trigger attached to one published version."""

    model_config = ConfigDict(extra="forbid")

    version_id: str = Field(min_length=1, max_length=64)


class WorkflowWebhookTriggerResponse(BaseModel):
    """Safe trigger representation for management views; it has no secret."""

    trigger_id: str
    workflow_id: str
    version_id: str
    org_id: str
    enabled: bool
    invoke_path: str
    created_by: str
    disabled_by: str | None
    disabled_at: datetime | None
    last_triggered_at: datetime | None
    created_at: datetime


class WorkflowWebhookTriggerCreatedResponse(WorkflowWebhookTriggerResponse):
    """Creation-only response.  The secret cannot be recovered later."""

    secret: str


class WorkflowWebhookInvocationResponse(BaseModel):
    """Acknowledgement for a verified external delivery."""

    run_id: str
    status: str
    accepted: bool = True
    idempotent_replay: bool = False
