"""Workflow run API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.api.app.domain.workflow_run import NodeRunStatus, RunStatus


class WorkflowRunCreateRequest(BaseModel):
    """Client-controlled workflow run inputs only."""

    model_config = ConfigDict(extra="forbid")

    version_id: str = Field(description="Published version ID")
    input_data: dict[str, Any] = Field(default_factory=dict, description="Run input")
    async_mode: bool = Field(default=False, description="Execute in Celery")


class WorkflowRunResponse(BaseModel):
    """Workflow run response."""

    run_id: str
    org_id: str
    workflow_id: str
    version_id: str
    agent_id: str
    input_data: dict[str, Any]
    status: RunStatus
    output_data: dict[str, Any]
    error_message: str
    celery_task_id: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime | None


class NodeRunResponse(BaseModel):
    """Workflow node execution response."""

    node_run_id: str
    run_id: str
    node_id: str
    node_type: str
    status: NodeRunStatus
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    error_message: str
    elapsed_ms: int
    sequence: int
