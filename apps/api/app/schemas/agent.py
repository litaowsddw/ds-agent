"""Agent 与 Workspace API Schema。"""

from pydantic import BaseModel, Field

from apps.api.app.domain.agent import WorkspaceFileKind


class AgentCreateRequest(BaseModel):
    """创建 Agent 请求。"""

    actor_user_id: str = Field(
        default="",
        description="Compatibility field; authenticated identity is used for authorization.",
    )
    org_id: str = Field(description="Agent 所属组织 ID")
    team_id: str | None = Field(default=None, description="Agent 所属群组 ID")
    name: str = Field(min_length=1, max_length=80, description="Agent 名称")
    description: str = Field(default="", max_length=500, description="Agent 描述")
    model_provider: str | None = Field(default=None, description="默认模型供应商 key")
    model_name: str | None = Field(default=None, description="默认模型名称")
    system_prompt: str | None = Field(default=None, description="系统提示词")
    temperature: float | None = Field(default=0.0, ge=0, le=2, description="采样温度")
    max_tokens: int | None = Field(default=None, ge=128, le=32768, description="最大输出 tokens")
    context_token_limit: int | None = Field(default=None, ge=800, le=2000000, description="上下文压缩阈值 tokens")
    default_workflow_id: str | None = Field(default=None, description="默认 Workflow ID，空值表示自主模式")


class AgentUpdateRequest(BaseModel):
    """更新 Agent 参数请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    name: str | None = Field(default=None, min_length=1, max_length=80, description="Agent 名称")
    description: str | None = Field(default=None, max_length=500, description="Agent 描述")
    model_provider: str | None = Field(default=None, description="默认模型供应商 key")
    model_name: str | None = Field(default=None, description="默认模型名称")
    system_prompt: str | None = Field(default=None, description="系统提示词")
    temperature: float | None = Field(default=None, ge=0, le=2, description="采样温度")
    max_tokens: int | None = Field(default=None, ge=128, le=32768, description="最大输出 tokens")
    context_token_limit: int | None = Field(default=None, ge=800, le=2000000, description="上下文压缩阈值 tokens")
    default_workflow_id: str | None = Field(default=None, description="默认 Workflow ID，空值表示自主模式")


class AgentResponse(BaseModel):
    """Agent 响应。"""

    agent_id: str
    org_id: str
    team_id: str | None
    name: str
    description: str
    kind: str = "USER_SUB"
    model_provider: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    context_token_limit: int | None = None
    default_workflow_id: str | None = None
    created_by: str


class WorkspaceResponse(BaseModel):
    """Agent Workspace 响应。"""

    workspace_id: str
    org_id: str
    agent_id: str
    files: dict[str, str]
    updated_by: str


class WorkspaceFileUpdateRequest(BaseModel):
    """更新 Workspace 文件请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    file_kind: WorkspaceFileKind = Field(description="Workspace 文件类型")
    content: str = Field(description="新的文件内容")
