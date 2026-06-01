"""Agent 与 Workspace API Schema。"""

from pydantic import BaseModel, Field

from apps.api.app.domain.agent import WorkspaceFileKind


class AgentCreateRequest(BaseModel):
    """创建 Agent 请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    org_id: str = Field(description="Agent 所属组织 ID")
    team_id: str | None = Field(default=None, description="Agent 所属群组 ID")
    name: str = Field(min_length=1, max_length=80, description="Agent 名称")
    description: str = Field(default="", max_length=500, description="Agent 描述")


class AgentResponse(BaseModel):
    """Agent 响应。"""

    agent_id: str
    org_id: str
    team_id: str | None
    name: str
    description: str
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
