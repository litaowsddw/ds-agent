"""MCP Registry API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.mcp import MCPServer, MCPTool
from apps.api.app.schemas.mcp import (
    AgentMCPPolicyRequest,
    MCPServerRegisterRequest,
    MCPServerResponse,
    MCPToolResponse,
    MCPToolSnapshotRequest,
)
from apps.api.app.services.mcp_store import mcp_store

router = APIRouter()


@router.post("/servers", response_model=MCPServerResponse)
async def register_server(request: MCPServerRegisterRequest) -> MCPServerResponse:
    """注册 MCP Server。"""

    try:
        server = mcp_store.register_server(
            actor_user_id=request.actor_user_id,
            org_id=request.org_id,
            name=request.name,
            transport=request.transport,
            url=request.url,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return _to_server_response(server)


@router.get("/servers", response_model=list[MCPServerResponse])
async def list_servers(
    org_id: str = Query(description="组织 ID"),
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[MCPServerResponse]:
    """列出组织内 MCP Server。"""

    try:
        servers = mcp_store.list_servers(actor_user_id=actor_user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_server_response(server) for server in servers]


@router.post("/servers/{server_id}/tools", response_model=MCPToolResponse)
async def upsert_tool_snapshot(server_id: str, request: MCPToolSnapshotRequest) -> MCPToolResponse:
    """写入 MCP Tool 快照。"""

    try:
        tool = mcp_store.upsert_tool_snapshot(
            actor_user_id=request.actor_user_id,
            server_id=server_id,
            name=request.name,
            description=request.description,
            input_schema=request.input_schema,
            risk_level=request.risk_level,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_tool_response(tool)


@router.put("/agents/{agent_id}/policy")
async def set_agent_mcp_policy(agent_id: str, request: AgentMCPPolicyRequest) -> dict[str, object]:
    """设置 Agent MCP 授权。"""

    try:
        policy = mcp_store.set_agent_mcp_policy(
            actor_user_id=request.actor_user_id,
            agent_id=agent_id,
            server_id=request.server_id,
            allowed=request.allowed,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"agent_id": policy.agent_id, "server_id": policy.server_id, "allowed": policy.allowed}


@router.get("/agents/{agent_id}/tools", response_model=list[MCPToolResponse])
async def list_agent_tools(
    agent_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[MCPToolResponse]:
    """列出 Agent 可用 MCP Tool。"""

    try:
        tools = mcp_store.list_agent_tools(actor_user_id=actor_user_id, agent_id=agent_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_tool_response(tool) for tool in tools]


@router.get("/agents/{agent_id}/tools/{tool_id}/can-call", response_model=MCPToolResponse)
async def assert_agent_can_call_tool(
    agent_id: str,
    tool_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> MCPToolResponse:
    """校验 Agent 是否可以调用指定 MCP Tool。"""

    try:
        tool = mcp_store.assert_agent_can_call_tool(
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            tool_id=tool_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return _to_tool_response(tool)


def _to_server_response(server: MCPServer) -> MCPServerResponse:
    """把 MCP Server 领域模型转换为 API 响应。"""

    return MCPServerResponse(
        server_id=server.server_id,
        org_id=server.org_id,
        name=server.name,
        transport=server.transport,
        url=server.url,
        enabled=server.enabled,
    )


def _to_tool_response(tool: MCPTool) -> MCPToolResponse:
    """把 MCP Tool 领域模型转换为 API 响应。"""

    return MCPToolResponse(
        tool_id=tool.tool_id,
        server_id=tool.server_id,
        org_id=tool.org_id,
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        risk_level=tool.risk_level,
    )

