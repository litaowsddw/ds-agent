"""后台 Agent API（数据库版本）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity import new_id
from app.models.runtime import BackgroundAgentModel
from app.schemas.background_agent import (
    BackgroundAgentRegisterRequest,
    BackgroundAgentResponse,
    BackgroundAgentTriggerRequest,
)
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import background_agent_db

router = APIRouter()


@router.post("", response_model=BackgroundAgentResponse)
async def register_background_agent(
    request: BackgroundAgentRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundAgentResponse:
    """注册后台 Agent 配置。"""

    try:
        await membership_db.assert_org_access(session, user_id=request.actor_user_id, org_id=request.org_id)
        config = await background_agent_db.create_config(
            session,
            config_id=new_id("bga"),
            org_id=request.org_id,
            agent_type=request.agent_type,
            interval_seconds=request.interval_seconds,
            enabled=True,
            created_by=request.actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(config)


@router.get("", response_model=list[BackgroundAgentResponse])
async def list_background_agents(
    org_id: str = Query(description="组织 ID"),
    actor_user_id: str = Query(description="操作用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[BackgroundAgentResponse]:
    """列出组织内后台 Agent 配置。"""

    try:
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=org_id)
        configs = await background_agent_db.list_org_configs(session, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [_to_response(config) for config in configs]


@router.post("/{config_id}/trigger", response_model=BackgroundAgentResponse)
async def trigger_background_agent(
    config_id: str,
    request: BackgroundAgentTriggerRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundAgentResponse:
    """手动触发后台 Agent。"""

    try:
        config = await background_agent_db.get_by_id_required(session, config_id, "config_id")
        await membership_db.assert_org_access(session, user_id=request.actor_user_id, org_id=config.org_id)
        config.status = "queued"
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(config)


@router.post("/{config_id}/disable", response_model=BackgroundAgentResponse)
async def disable_background_agent(
    config_id: str,
    request: BackgroundAgentTriggerRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BackgroundAgentResponse:
    """禁用后台 Agent。"""

    try:
        config = await background_agent_db.get_by_id_required(session, config_id, "config_id")
        await membership_db.assert_org_access(session, user_id=request.actor_user_id, org_id=config.org_id)
        config.enabled = False
        config.status = "disabled"
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(config)


def _to_response(config: BackgroundAgentModel) -> BackgroundAgentResponse:
    """把后台 Agent ORM 模型转换成 API 响应。"""

    return BackgroundAgentResponse(
        config_id=config.config_id,
        org_id=config.org_id,
        agent_type=config.agent_type,
        enabled=config.enabled,
        interval_seconds=config.interval_seconds,
        status=config.status,
        last_error="",
    )
