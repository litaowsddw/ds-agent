"""后台 Agent API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.background_agent import (
    BackgroundAgentConfig,
    BackgroundAgentType,
)
from apps.api.app.schemas.background_agent import (
    BackgroundAgentRegisterRequest,
    BackgroundAgentResponse,
    BackgroundAgentTriggerRequest,
)
from apps.api.app.services.background_agent_store import (
    background_agent_store,
)

router = APIRouter()


@router.post("", response_model=BackgroundAgentResponse)
async def register_background_agent(
    request: BackgroundAgentRegisterRequest,
) -> BackgroundAgentResponse:
    """注册后台 Agent。"""
    try:
        config = background_agent_store.register_agent(
            actor_user_id=request.actor_user_id,
            org_id=request.org_id,
            agent_type=BackgroundAgentType(request.agent_type),
            interval_seconds=request.interval_seconds,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(config)


@router.get("", response_model=list[BackgroundAgentResponse])
async def list_background_agents(
    org_id: str = Query(description="组织 ID"),
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[BackgroundAgentResponse]:
    """列出组织内后台 Agent。"""
    try:
        configs = background_agent_store.list_agents(actor_user_id=actor_user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [_to_response(c) for c in configs]


@router.post(
    "/{config_id}/trigger",
    response_model=BackgroundAgentResponse,
)
async def trigger_background_agent(
    config_id: str, request: BackgroundAgentTriggerRequest
) -> BackgroundAgentResponse:
    """手动触发后台 Agent 运行。"""
    try:
        config = background_agent_store.trigger_run(
            actor_user_id=request.actor_user_id,
            config_id=config_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(config)


@router.post(
    "/{config_id}/disable",
    response_model=BackgroundAgentResponse,
)
async def disable_background_agent(
    config_id: str, request: BackgroundAgentTriggerRequest
) -> BackgroundAgentResponse:
    """禁用后台 Agent。"""
    try:
        config = background_agent_store.disable_agent(
            actor_user_id=request.actor_user_id,
            config_id=config_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(config)


def _to_response(
    config: BackgroundAgentConfig,
) -> BackgroundAgentResponse:
    return BackgroundAgentResponse(
        config_id=config.config_id,
        org_id=config.org_id,
        agent_type=config.agent_type,
        enabled=config.enabled,
        interval_seconds=config.interval_seconds,
        status=config.status,
        last_error=config.last_error,
    )
