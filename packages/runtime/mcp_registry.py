"""MCP 服务注册表。

MCPRegistry 负责管理外部 MCP Server，并为 Agent Runtime 暴露经过授权的工具。
"""

from dataclasses import dataclass


@dataclass(slots=True)
class MCPServerDescriptor:
    """MCP Server 描述。"""

    # server_id 是 MCP Server 的唯一标识。
    server_id: str

    # name 是 MCP Server 展示名称。
    name: str

    # transport 表示通信方式，例如 http、sse、streamable_http。
    transport: str

    # url 是远程 MCP Server 地址。
    url: str


class MCPRegistry:
    """负责 MCP Server 注册、发现和健康检查。"""

    def list_servers(self, org_id: str) -> list[MCPServerDescriptor]:
        """列出组织内已注册的 MCP Server。"""

        # org_id 是 MCP Server 的租户隔离边界。
        _org_id = org_id

        return []
