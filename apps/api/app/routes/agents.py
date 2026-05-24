"""Agent 与 Workspace API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.agent import Agent, AgentWorkspace
from apps.api.app.schemas.agent import (
    AgentCreateRequest,
    AgentResponse,
    WorkspaceFileUpdateRequest,
    WorkspaceResponse,
)
from apps.api.app.services.agent_store import agent_store

router = APIRouter()


@router.post("", response_model=AgentResponse)
async def create_agent(request: AgentCreateRequest) -> AgentResponse:
    """创建 Agent。"""

    try:
        agent = agent_store.create_agent(
            actor_user_id=request.actor_user_id,
            org_id=request.org_id,
            team_id=request.team_id,
            name=request.name,
            description=request.description,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_agent_response(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    org_id: str = Query(description="组织 ID"),
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[AgentResponse]:
    """列出组织内 Agent。"""

    try:
        agents = agent_store.list_agents(actor_user_id=actor_user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_agent_response(agent) for agent in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> AgentResponse:
    """读取 Agent。"""

    try:
        agent = agent_store.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_agent_response(agent)


@router.get("/{agent_id}/workspace", response_model=WorkspaceResponse)
async def get_workspace(
    agent_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> WorkspaceResponse:
    """读取 Agent Workspace。"""

    try:
        workspace = agent_store.get_workspace(actor_user_id=actor_user_id, agent_id=agent_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_workspace_response(workspace)


@router.put("/{agent_id}/workspace/file", response_model=WorkspaceResponse)
async def update_workspace_file(
    agent_id: str,
    request: WorkspaceFileUpdateRequest,
) -> WorkspaceResponse:
    """更新 Agent Workspace 文件。"""

    try:
        workspace = agent_store.update_workspace_file(
            actor_user_id=request.actor_user_id,
            agent_id=agent_id,
            file_kind=request.file_kind,
            content=request.content,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_workspace_response(workspace)


def _to_agent_response(agent: Agent) -> AgentResponse:
    """把 Agent 领域模型转换为 API 响应。"""

    return AgentResponse(
        agent_id=agent.agent_id,
        org_id=agent.org_id,
        team_id=agent.team_id,
        name=agent.name,
        description=agent.description,
        created_by=agent.created_by,
    )


def _to_workspace_response(workspace: AgentWorkspace) -> WorkspaceResponse:
    """把 Workspace 领域模型转换为 API 响应。"""

    return WorkspaceResponse(
        workspace_id=workspace.workspace_id,
        org_id=workspace.org_id,
        agent_id=workspace.agent_id,
        files={file_kind.value: content for file_kind, content in workspace.files.items()},
        updated_by=workspace.updated_by,
    )
