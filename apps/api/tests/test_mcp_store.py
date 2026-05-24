"""MCPStore 测试。"""

import pytest

from apps.api.app.domain.mcp import MCPTransport
from apps.api.app.services.agent_store import AgentStore
from apps.api.app.services.identity_store import IdentityStore
from apps.api.app.services.mcp_store import MCPStore


def test_agent_can_list_allowed_mcp_tools() -> None:
    """Agent 被授权 MCP Server 后可以看到该 Server 的工具。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    mcp_store = MCPStore(identity=identity, agents=agent_store)

    owner = identity.register_user("mcp-owner@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "MCP 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "MCP Agent", "")
    server = mcp_store.register_server(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        name="工具服务",
        transport=MCPTransport.STREAMABLE_HTTP,
        url="http://mcp.example.com",
    )
    tool = mcp_store.upsert_tool_snapshot(
        actor_user_id=owner.user_id,
        server_id=server.server_id,
        name="search_docs",
        description="搜索文档",
        input_schema={"type": "object"},
    )
    mcp_store.set_agent_mcp_policy(owner.user_id, agent.agent_id, server.server_id, True)

    tools = mcp_store.list_agent_tools(owner.user_id, agent.agent_id)

    assert tools[0].tool_id == tool.tool_id


def test_agent_cannot_call_unallowed_mcp_tool() -> None:
    """未授权 MCP Tool 调用应被拒绝。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    mcp_store = MCPStore(identity=identity, agents=agent_store)

    owner = identity.register_user("mcp-block@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "MCP Block 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "MCP Block Agent", "")
    server = mcp_store.register_server(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        name="未授权服务",
        transport=MCPTransport.HTTP,
        url="http://mcp-block.example.com",
    )
    tool = mcp_store.upsert_tool_snapshot(
        actor_user_id=owner.user_id,
        server_id=server.server_id,
        name="danger_tool",
        description="未授权工具",
        input_schema={"type": "object"},
    )

    with pytest.raises(PermissionError):
        mcp_store.assert_agent_can_call_tool(owner.user_id, agent.agent_id, tool.tool_id)

