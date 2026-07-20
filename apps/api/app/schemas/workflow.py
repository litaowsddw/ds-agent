"""Workflow API Schema。"""

from pydantic import BaseModel, Field


class WorkflowCreateRequest(BaseModel):
    """创建 Workflow 请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    agent_id: str = Field(description="绑定 Agent ID")
    name: str = Field(min_length=1, max_length=120, description="工作流名称")
    description: str = Field(default="", max_length=500, description="工作流说明")
    draft_definition: dict[str, object] = Field(description="工作流草稿 DSL")


class WorkflowUpdateDraftRequest(BaseModel):
    """更新 Workflow 草稿请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    draft_definition: dict[str, object] = Field(description="工作流草稿 DSL")


class WorkflowPublishRequest(BaseModel):
    """发布 Workflow 请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")


class WorkflowValidateRequest(BaseModel):
    """Validate a canvas draft without saving or publishing it."""

    actor_user_id: str = Field(description="操作用户 ID")
    draft_definition: dict[str, object] = Field(description="待校验的 Workflow DSL")


class WorkflowValidationResponse(BaseModel):
    """Workflow preflight result."""

    valid: bool
    errors: list[str]


class WorkflowResponse(BaseModel):
    """Workflow 响应。"""

    workflow_id: str
    org_id: str
    agent_id: str
    name: str
    description: str
    draft_definition: dict[str, object]
    published_version_id: str | None
    created_by: str


class WorkflowVersionResponse(BaseModel):
    """Workflow Version 响应。"""

    version_id: str
    workflow_id: str
    org_id: str
    version_number: int
    definition: dict[str, object]
    created_by: str
