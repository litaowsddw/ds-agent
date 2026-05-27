"""Workflow Run API Schema。"""

from typing import Any

from pydantic import BaseModel, Field

from apps.api.app.domain.workflow_run import NodeRunStatus, RunStatus


class WorkflowRunCreateRequest(BaseModel):
    """创建 Workflow Run 请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    version_id: str = Field(description="发布版本 ID")
    input_data: dict[str, Any] = Field(default_factory=dict, description="运行输入")
    async_mode: bool = Field(default=False, description="是否投递到 Celery 异步执行")


class WorkflowRunResponse(BaseModel):
    """Workflow Run 响应。"""

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


class NodeRunResponse(BaseModel):
    """Node Run 响应。"""

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
