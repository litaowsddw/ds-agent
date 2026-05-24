"""MCP Registry MVP 存储。"""

from apps.api.app.domain.identity import new_id
from apps.api.app.domain.mcp import AgentMCPPolicy, MCPServer, MCPTool, MCPTransport
from apps.api.app.services.agent_store import AgentStore, agent_store
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission


class MCPStore:
    """管理 MCP Server、工具快照和 Agent 授权。"""

    def __init__(self, identity: IdentityStore, agents: AgentStore) -> None:
        # identity 用于组织权限校验。
        self.identity = identity

        # agents 用于读取 Agent 所属组织。
        self.agents = agents

        # servers_by_id 保存 MCP Server。
        self.servers_by_id: dict[str, MCPServer] = {}

        # tools_by_id 保存 MCP Tool 快照。
        self.tools_by_id: dict[str, MCPTool] = {}

        # policies_by_agent_server 保存 Agent 到 MCP Server 的授权策略。
        self.policies_by_agent_server: dict[str, AgentMCPPolicy] = {}

    def register_server(
        self,
        actor_user_id: str,
        org_id: str,
        name: str,
        transport: MCPTransport,
        url: str,
    ) -> MCPServer:
        """注册 MCP Server。"""

        self.identity.assert_org_access(actor_user_id, org_id, Permission.AGENT_CREATE)

        server = MCPServer(
            server_id=new_id("mcp"),
            org_id=org_id,
            name=name.strip(),
            transport=transport,
            url=url.strip(),
            created_by=actor_user_id,
        )
        self.servers_by_id[server.server_id] = server
        return server

    def upsert_tool_snapshot(
        self,
        actor_user_id: str,
        server_id: str,
        name: str,
        description: str,
        input_schema: dict[str, object],
        risk_level: str = "low",
    ) -> MCPTool:
        """写入 MCP Tool 快照。"""

        server = self._require_server(server_id)
        self.identity.assert_org_access(actor_user_id, server.org_id, Permission.AGENT_CREATE)

        tool = MCPTool(
            tool_id=new_id("tool"),
            server_id=server.server_id,
            org_id=server.org_id,
            name=name.strip(),
            description=description.strip(),
            input_schema=input_schema,
            risk_level=risk_level,
        )
        self.tools_by_id[tool.tool_id] = tool
        return tool

    def set_agent_mcp_policy(
        self,
        actor_user_id: str,
        agent_id: str,
        server_id: str,
        allowed: bool,
    ) -> AgentMCPPolicy:
        """设置 Agent MCP Server 授权策略。"""

        agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
        server = self._require_server(server_id)
        if server.org_id != agent.org_id:
            raise ValueError("MCP Server 不属于该 Agent 的组织")

        self.identity.assert_org_access(actor_user_id, agent.org_id, Permission.AGENT_CREATE)

        policy = AgentMCPPolicy(agent_id=agent_id, server_id=server_id, allowed=allowed)
        self.policies_by_agent_server[self._policy_key(agent_id, server_id)] = policy
        return policy

    def list_agent_tools(self, actor_user_id: str, agent_id: str) -> list[MCPTool]:
        """列出 Agent 可用 MCP Tool。"""

        agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)

        allowed_server_ids = {
            policy.server_id
            for policy in self.policies_by_agent_server.values()
            if policy.agent_id == agent.agent_id and policy.allowed
        }

        return [
            tool
            for tool in sorted(self.tools_by_id.values(), key=lambda item: item.name)
            if tool.org_id == agent.org_id and tool.server_id in allowed_server_ids
        ]

    def assert_agent_can_call_tool(self, actor_user_id: str, agent_id: str, tool_id: str) -> MCPTool:
        """校验 Agent 是否可以调用 MCP Tool。"""

        allowed_tools = self.list_agent_tools(actor_user_id=actor_user_id, agent_id=agent_id)
        for tool in allowed_tools:
            if tool.tool_id == tool_id:
                return tool

        raise PermissionError("Agent 未被授权调用该 MCP Tool")

    def _require_server(self, server_id: str) -> MCPServer:
        """要求 MCP Server 必须存在。"""

        server = self.servers_by_id.get(server_id)
        if server is None:
            raise ValueError("MCP Server 不存在")
        return server

    def _policy_key(self, agent_id: str, server_id: str) -> str:
        """生成 Agent-MCP 授权索引键。"""

        return f"{agent_id}:{server_id}"


# mcp_store 是 MVP 阶段的进程内 MCP Registry。
mcp_store = MCPStore(identity=identity_store, agents=agent_store)

