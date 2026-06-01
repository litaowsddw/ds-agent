"""Agent 与 Workspace API（数据库版本）。

使用 SQLAlchemy 异步数据库服务替代内存 store。
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.agent import AgentModel, AgentWorkspaceModel
from app.schemas.agent import (
    AgentCreateRequest,
    AgentResponse,
    WorkspaceFileUpdateRequest,
    WorkspaceResponse,
)
from app.services.db.agent_db import agent_db, workspace_db
from app.services.db.identity_db import membership_db
from app.domain.identity import new_id

router = APIRouter()


@router.post("", response_model=AgentResponse)
async def create_agent(
    request: AgentCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AgentResponse:
    """创建 Agent。"""
    try:
        # 权限校验
        await membership_db.assert_org_access(
            session, user_id=request.actor_user_id, org_id=request.org_id
        )

        agent = await agent_db.create_agent(
            session,
            agent_id=new_id("agt"),
            org_id=request.org_id,
            team_id=request.team_id,
            name=request.name,
            description=request.description,
            created_by=request.actor_user_id,
        )

        # 自动创建 Workspace
        await workspace_db.create_workspace(
            session,
            workspace_id=new_id("wsp"),
            org_id=request.org_id,
            agent_id=agent.agent_id,
            updated_by=request.actor_user_id,
        )

        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_agent_response(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    org_id: str = Query(description="组织 ID"),
    actor_user_id: str = Query(description="操作者用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentResponse]:
    """列出组织内 Agent。"""
    try:
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=org_id
        )
        agents = await agent_db.list_org_agents(session, org_id=org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_agent_response(agent) for agent in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> AgentResponse:
    """读取 Agent。"""
    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=agent.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_agent_response(agent)


@router.get("/{agent_id}/workspace", response_model=WorkspaceResponse)
async def get_workspace(
    agent_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """读取 Agent Workspace。"""
    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=agent.org_id
        )
        workspace = await workspace_db.get_by_agent_id_required(session, agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_workspace_response(workspace)


@router.put("/{agent_id}/workspace/file", response_model=WorkspaceResponse)
async def update_workspace_file(
    agent_id: str,
    request: WorkspaceFileUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """更新 Agent Workspace 文件。"""
    # file_kind 到数据库字段的映射
    kind_to_field = {
        "AGENTS": "agents_md",
        "SOUL": "soul_md",
        "TOOLS": "tools_md",
        "MEMORY": "memory_md",
    }

    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        await membership_db.assert_org_access(
            session, user_id=request.actor_user_id, org_id=agent.org_id
        )

        field_name = kind_to_field.get(request.file_kind)
        if field_name is None:
            raise ValueError(f"不支持的文件类型：{request.file_kind}")

        workspace = await workspace_db.update_workspace_file(
            session, agent_id=agent_id, file_field=field_name,
            content=request.content, updated_by=request.actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_workspace_response(workspace)


def _to_agent_response(agent: AgentModel) -> AgentResponse:
    """把 Agent ORM 模型转换为 API 响应。"""
    return AgentResponse(
        agent_id=agent.agent_id,
        org_id=agent.org_id,
        team_id=agent.team_id,
        name=agent.name,
        description=agent.description or "",
        created_by=agent.created_by,
    )


def _to_workspace_response(workspace: AgentWorkspaceModel) -> WorkspaceResponse:
    """把 Workspace ORM 模型转换为 API 响应。"""
    return WorkspaceResponse(
        workspace_id=workspace.workspace_id,
        org_id=workspace.org_id,
        agent_id=workspace.agent_id,
        files={
            "AGENTS": workspace.agents_md,
            "SOUL": workspace.soul_md,
            "TOOLS": workspace.tools_md,
            "MEMORY": workspace.memory_md,
        },
        updated_by=workspace.updated_by,
    )
