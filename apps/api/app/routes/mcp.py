"""MCP Registry API。

MCP Server、Tool 快照与 Agent 授权策略全部写入数据库，前端看到的数据和
Workflow Tool 节点执行时读取的数据保持一致。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.core.security import encrypt_api_key
from app.domain.identity import new_id
from app.domain.mcp import MCPTransport
from app.models.runtime import AgentMCPPolicyModel, MCPServerModel, MCPToolModel
from app.schemas.mcp import (
    AgentMCPPolicyRequest,
    MCPAgentImportRequest,
    MCPAgentImportResponse,
    MCPServerRegisterRequest,
    MCPServerResponse,
    MCPToolResponse,
    MCPToolSnapshotRequest,
)
from app.services.db.agent_db import agent_db
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import agent_mcp_policy_db, mcp_server_db, mcp_tool_db
from app.services.external_import import ExternalImportError, discover_streamable_http_tools
from app.core.auth import AuthenticatedUser, resolve_actor, CurrentUser

router = APIRouter()


@router.post("/agents/{agent_id}/import", response_model=MCPAgentImportResponse)
async def import_agent_mcp(
    agent_id: str,
    request: MCPAgentImportRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> MCPAgentImportResponse:
    """Discover an external MCP service and bind its tools to one Agent.

    This endpoint only imports the declared tools.  Runtime tools/call is kept
    separate so a discovery request cannot trigger third-party side effects.
    """

    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        agent = await agent_db.get_agent_required(session, agent_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=agent.org_id
        )
        if request.transport != MCPTransport.STREAMABLE_HTTP:
            raise ValueError("当前仅支持 streamable_http MCP 导入；SSE/stdio 需要受管连接器")
        credential_headers = _credential_headers(request)
        discovered_tools = discover_streamable_http_tools(request.url, credential_headers)
        server = await mcp_server_db.create_server(
            session,
            server_id=new_id("mcp"),
            org_id=agent.org_id,
            name=request.name,
            transport=request.transport.value,
            url=request.url,
            credentials_encrypted=encrypt_api_key(json.dumps(credential_headers, ensure_ascii=False)),
            created_by=actor_user_id,
        )
        tools = []
        for discovered in discovered_tools:
            tool = await mcp_tool_db.create_tool(
                session,
                tool_id=new_id("tool"),
                server_id=server.server_id,
                name=discovered.name,
                description=discovered.description,
                input_schema=discovered.input_schema,
                risk_level="low",
                created_by=actor_user_id,
            )
            tools.append(tool)
        await agent_mcp_policy_db.set_policy(
            session, agent_id=agent.agent_id, server_id=server.server_id, allowed=True
        )
        await session.commit()
    except (ValueError, ExternalImportError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MCPAgentImportResponse(
        server=_to_server_response(server),
        tools=[_to_tool_response(tool, agent.org_id) for tool in tools],
        agent_id=agent.agent_id,
    )


@router.post("/servers", response_model=MCPServerResponse)
async def register_server(
    request: MCPServerRegisterRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> MCPServerResponse:
    """注册 MCP Server。"""

    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=request.org_id
        )
        if request.transport == MCPTransport.STREAMABLE_HTTP:
            raise ValueError(
                "streamable_http MCP 必须通过 /mcp/agents/{agent_id}/import 受控导入并绑定 Agent"
            )
        server = await mcp_server_db.create_server(
            session,
            server_id=new_id("mcp"),
            org_id=request.org_id,
            name=request.name,
            transport=str(request.transport.value if hasattr(request.transport, "value") else request.transport),
            url=request.url,
            created_by=actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_server_response(server)


@router.get("/servers", response_model=list[MCPServerResponse])
async def list_servers(
    auth: AuthenticatedUser,
    org_id: str = Query(description="组织 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[MCPServerResponse]:
    """列出组织内 MCP Server。"""

    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=org_id
        )
        servers = await mcp_server_db.list_org_servers(session, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_server_response(server) for server in servers]


@router.post("/servers/{server_id}/tools", response_model=MCPToolResponse)
async def upsert_tool_snapshot(
    server_id: str,
    request: MCPToolSnapshotRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> MCPToolResponse:
    """写入 MCP Tool 快照。"""

    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        server = await mcp_server_db.get_by_id_required(session, server_id, "server_id")
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=server.org_id
        )
        tool = await mcp_tool_db.create_tool(
            session,
            tool_id=new_id("tool"),
            server_id=server_id,
            name=request.name,
            description=request.description,
            input_schema=request.input_schema,
            risk_level=request.risk_level,
            created_by=actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_tool_response(tool=tool, org_id=server.org_id)


@router.put("/agents/{agent_id}/policy")
async def set_agent_mcp_policy(
    agent_id: str,
    request: AgentMCPPolicyRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """设置 Agent MCP 授权。"""

    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        server = await mcp_server_db.get_by_id_required(session, request.server_id, "server_id")
        if agent.org_id != server.org_id:
            raise ValueError("Agent 和 MCP Server 不属于同一组织")
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=agent.org_id
        )
        policy = await agent_mcp_policy_db.set_policy(
            session,
            agent_id=agent_id,
            server_id=request.server_id,
            allowed=request.allowed,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"agent_id": policy.agent_id, "server_id": policy.server_id, "allowed": policy.allowed}


@router.get("/agents/{agent_id}/tools", response_model=list[MCPToolResponse])
async def list_agent_tools(
    agent_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[MCPToolResponse]:
    """列出 Agent 可用 MCP Tool。"""

    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=agent.org_id
        )
        tools = await _list_allowed_tools(session, agent_id=agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_tool_response(tool=tool, org_id=agent.org_id) for tool in tools]


@router.get("/agents/{agent_id}/tools/{tool_id}/can-call", response_model=MCPToolResponse)
async def assert_agent_can_call_tool(
    agent_id: str,
    tool_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> MCPToolResponse:
    """校验 Agent 是否可以调用指定 MCP Tool。"""

    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=agent.org_id
        )
        tool = await _get_allowed_tool(session, agent_id=agent_id, tool_id=tool_id)
        if tool is None:
            raise ValueError("Agent 未授权调用该 MCP Tool")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return _to_tool_response(tool=tool, org_id=agent.org_id)


async def _list_allowed_tools(session: AsyncSession, agent_id: str) -> list[MCPToolModel]:
    """读取 Agent 已授权 Server 下的所有 Tool。"""

    stmt = (
        select(MCPToolModel)
        .join(MCPServerModel, MCPToolModel.server_id == MCPServerModel.server_id)
        .join(AgentMCPPolicyModel, AgentMCPPolicyModel.server_id == MCPServerModel.server_id)
        .where(
            AgentMCPPolicyModel.agent_id == agent_id,
            AgentMCPPolicyModel.allowed == True,
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _get_allowed_tool(
    session: AsyncSession, agent_id: str, tool_id: str
) -> MCPToolModel | None:
    """读取一个已授权 Tool。"""

    stmt = (
        select(MCPToolModel)
        .join(MCPServerModel, MCPToolModel.server_id == MCPServerModel.server_id)
        .join(AgentMCPPolicyModel, AgentMCPPolicyModel.server_id == MCPServerModel.server_id)
        .where(
            AgentMCPPolicyModel.agent_id == agent_id,
            AgentMCPPolicyModel.allowed == True,
            MCPToolModel.tool_id == tool_id,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _to_server_response(server: MCPServerModel) -> MCPServerResponse:
    """把 MCP Server ORM 模型转换为 API 响应。"""

    return MCPServerResponse(
        server_id=server.server_id,
        org_id=server.org_id,
        name=server.name,
        transport=server.transport,
        url=server.url,
        enabled=True,
    )


def _credential_headers(request: MCPAgentImportRequest) -> dict[str, str]:
    """Turn explicit credential fields into outbound MCP headers only in memory."""

    headers = dict(request.credentials.headers)
    if request.credentials.bearer_token:
        headers["Authorization"] = f"Bearer {request.credentials.bearer_token}"
    if request.credentials.api_key:
        headers["X-API-Key"] = request.credentials.api_key
    return headers


def _to_tool_response(tool: MCPToolModel, org_id: str) -> MCPToolResponse:
    """把 MCP Tool ORM 模型转换为 API 响应。"""

    return MCPToolResponse(
        tool_id=tool.tool_id,
        server_id=tool.server_id,
        org_id=org_id,
        name=tool.name,
        description=tool.description,
        input_schema=json.loads(tool.input_schema or "{}"),
        risk_level=tool.risk_level,
    )
