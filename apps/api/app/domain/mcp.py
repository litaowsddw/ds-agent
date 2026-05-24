"""MCP 领域模型。

MCP Registry 负责把外部 MCP Server 安全地挂到 Agent Runtime 中。
MVP 阶段先实现注册、工具快照和 Agent 授权，不直接发起远程调用。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from apps.api.app.domain.identity import utc_now


class MCPTransport(StrEnum):
    """MCP 通信方式。"""

    HTTP = "http"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


@dataclass(slots=True)
class MCPServer:
    """MCP Server 实体。"""

    # server_id 是 MCP Server 唯一标识。
    server_id: str

    # org_id 是 MCP Server 所属组织。
    org_id: str

    # name 是 MCP Server 名称。
    name: str

    # transport 是 MCP 通信方式。
    transport: MCPTransport

    # url 是 MCP Server 地址。
    url: str

    # created_by 是创建者用户 ID。
    created_by: str

    # enabled 表示该 MCP Server 是否启用。
    enabled: bool = True

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class MCPTool:
    """MCP Tool 快照。"""

    # tool_id 是工具快照唯一标识。
    tool_id: str

    # server_id 是工具所属 MCP Server。
    server_id: str

    # org_id 是工具所属组织。
    org_id: str

    # name 是工具名称。
    name: str

    # description 是工具说明。
    description: str

    # input_schema 是工具输入 JSON Schema。
    input_schema: dict[str, object]

    # risk_level 是工具风险等级，后续用于人工确认策略。
    risk_level: str = "low"


@dataclass(slots=True)
class AgentMCPPolicy:
    """Agent MCP Server 授权策略。"""

    # agent_id 是被授权 Agent。
    agent_id: str

    # server_id 是授权的 MCP Server。
    server_id: str

    # allowed 表示是否允许 Agent 使用该 MCP Server。
    allowed: bool

