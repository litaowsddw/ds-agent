"""MCP API Schema。"""

from pydantic import BaseModel, Field

from apps.api.app.domain.mcp import MCPTransport


class MCPServerRegisterRequest(BaseModel):
    """注册 MCP Server 请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    org_id: str = Field(description="组织 ID")
    name: str = Field(min_length=1, max_length=80, description="MCP Server 名称")
    transport: MCPTransport = Field(description="MCP 通信方式")
    url: str = Field(description="MCP Server 地址")


class MCPConnectionCredentials(BaseModel):
    """Credentials held server-side and never returned by the API."""

    bearer_token: str | None = Field(default=None, max_length=4096)
    api_key: str | None = Field(default=None, max_length=4096)
    headers: dict[str, str] = Field(default_factory=dict)


class MCPAgentImportRequest(BaseModel):
    """Connect one Agent to a third-party Streamable HTTP MCP endpoint."""

    actor_user_id: str = Field(description="操作用户 ID")
    name: str = Field(min_length=1, max_length=80, description="MCP 服务展示名称")
    transport: MCPTransport = Field(default=MCPTransport.STREAMABLE_HTTP)
    url: str = Field(max_length=512, description="外部 MCP HTTPS 地址")
    credentials: MCPConnectionCredentials = Field(default_factory=MCPConnectionCredentials)


class MCPServerResponse(BaseModel):
    """MCP Server 响应。"""

    server_id: str
    org_id: str
    name: str
    transport: MCPTransport
    url: str
    enabled: bool


class MCPToolSnapshotRequest(BaseModel):
    """写入 MCP Tool 快照请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    name: str = Field(description="工具名称")
    description: str = Field(description="工具说明")
    input_schema: dict[str, object] = Field(description="工具输入 JSON Schema")
    risk_level: str = Field(default="low", description="工具风险等级")


class MCPToolResponse(BaseModel):
    """MCP Tool 响应。"""

    tool_id: str
    server_id: str
    org_id: str
    name: str
    description: str
    input_schema: dict[str, object]
    risk_level: str


class AgentMCPPolicyRequest(BaseModel):
    """Agent MCP 授权请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    server_id: str = Field(description="MCP Server ID")
    allowed: bool = Field(description="是否允许使用")


class MCPAgentImportResponse(BaseModel):
    server: MCPServerResponse
    tools: list[MCPToolResponse]
    agent_id: str
