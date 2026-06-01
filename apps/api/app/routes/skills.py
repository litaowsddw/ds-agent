"""Skill API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.skill import Skill
from apps.api.app.schemas.skill import (
    AgentSkillPolicyRequest,
    SkillRegisterRequest,
    SkillResponse,
    SkillSummaryResponse,
)
from apps.api.app.services.skill_store import skill_store

router = APIRouter()


@router.post("", response_model=SkillResponse)
async def register_skill(request: SkillRegisterRequest) -> SkillResponse:
    """注册 Skill。"""

    try:
        skill = skill_store.register_skill(
            actor_user_id=request.actor_user_id,
            org_id=request.org_id,
            scope=request.scope,
            content=request.content,
            team_id=request.team_id,
            agent_id=request.agent_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_skill_response(skill)


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    org_id: str = Query(description="组织 ID"),
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[SkillResponse]:
    """列出组织内可见的 Skill。"""

    try:
        skills = skill_store.list_skills(actor_user_id=actor_user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_skill_response(skill) for skill in skills]


@router.put("/agents/{agent_id}/policy")
async def set_agent_skill_policy(
    agent_id: str, request: AgentSkillPolicyRequest
) -> dict[str, object]:
    """设置 Agent Skill 授权策略。"""

    try:
        policy = skill_store.set_agent_skill_policy(
            actor_user_id=request.actor_user_id,
            agent_id=agent_id,
            skill_id=request.skill_id,
            allowed=request.allowed,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"agent_id": policy.agent_id, "skill_id": policy.skill_id, "allowed": policy.allowed}


@router.get("/agents/{agent_id}/summaries", response_model=list[SkillSummaryResponse])
async def list_agent_skill_summaries(
    agent_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[SkillSummaryResponse]:
    """列出 Agent 可用 Skill 摘要。"""

    try:
        summaries = skill_store.list_allowed_skill_summaries(
            actor_user_id=actor_user_id,
            agent_id=agent_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [SkillSummaryResponse(**summary) for summary in summaries]


@router.get("/agents/{agent_id}/skills/{skill_id}", response_model=SkillResponse)
async def get_agent_skill(
    agent_id: str,
    skill_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> SkillResponse:
    """读取 Agent 已授权 Skill 的完整元信息。"""

    try:
        skill = skill_store.get_skill_content(
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            skill_id=skill_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_skill_response(skill)


def _to_skill_response(skill: Skill) -> SkillResponse:
    """把 Skill 领域模型转换为 API 响应。"""

    return SkillResponse(
        skill_id=skill.skill_id,
        org_id=skill.org_id,
        team_id=skill.team_id,
        agent_id=skill.agent_id,
        scope=skill.scope,
        name=skill.name,
        description=skill.description,
        enabled=skill.enabled,
    )
