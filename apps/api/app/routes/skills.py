"""Skill API（数据库版本）。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity import new_id
from app.models.runtime import SkillModel
from app.schemas.skill import (
    AgentSkillPolicyRequest,
    SkillImportRequest,
    SkillRegisterRequest,
    SkillResponse,
    SkillSummaryResponse,
)
from app.services.db.agent_db import agent_db
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import agent_skill_policy_db, skill_db
from app.services.external_import import ExternalImportError, fetch_github_skill
from app.core.auth import AuthenticatedUser, resolve_actor, CurrentUser

router = APIRouter()


@router.post("", response_model=SkillResponse)
async def register_skill(
    request: SkillRegisterRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> SkillResponse:
    """注册 Skill。"""

    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=request.org_id
        )
        if request.agent_id:
            agent = await agent_db.get_agent_required(session, request.agent_id)
            if agent.org_id != request.org_id:
                raise ValueError("Agent 不属于该组织")

        metadata = _parse_skill_markdown(request.content)
        skill = await skill_db.create_skill(
            session,
            skill_id=new_id("skl"),
            org_id=request.org_id,
            team_id=request.team_id,
            agent_id=request.agent_id,
            scope=str(request.scope.value if hasattr(request.scope, "value") else request.scope),
            name=metadata["name"],
            description=metadata["description"],
            content=request.content,
            created_by=actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_skill_response(skill)


@router.post("/import", response_model=SkillResponse)
async def import_github_skill(
    request: SkillImportRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> SkillResponse:
    """Import exactly one public GitHub SKILL.md and authorize the target Agent.

    The downloader is intentionally narrow: no arbitrary URLs, redirects, or
    repository-wide cloning.  A user must provide the exact file to review.
    """

    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=request.org_id)
        agent = await agent_db.get_agent_required(session, request.agent_id)
        if agent.org_id != request.org_id:
            raise ValueError("Agent 不属于该组织")
        content, resolved_source = fetch_github_skill(request.source_url)
        metadata = _parse_skill_markdown(content)
        skill = await skill_db.create_skill(
            session,
            skill_id=new_id("skl"),
            org_id=request.org_id,
            scope="agent",
            name=metadata["name"],
            description=metadata["description"],
            content=content,
            agent_id=agent.agent_id,
            # Do not expose a remote URL as a local resource directory.  The
            # imported SKILL.md lives in the database and its instructions are
            # still available to progressive disclosure.
            file_path=None,
            created_by=actor_user_id,
        )
        await agent_skill_policy_db.set_policy(
            session, agent_id=agent.agent_id, skill_id=skill.skill_id, allowed=True
        )
        await session.commit()
    except (ValueError, ExternalImportError) as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_skill_response(skill)


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    auth: AuthenticatedUser,
    org_id: str = Query(description="组织 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[SkillResponse]:
    """列出组织内可见 Skill。"""

    try:
        await membership_db.assert_org_access(session, user_id=auth.user_id, org_id=org_id)
        skills = await skill_db.list_org_skills(session, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 平台内置 Skill 对所有组织可见（opencode 默认 Skill 思路），不落库。
    from apps.api.app.domain.skill import SkillScope
    from app.services.bundled_skills import list_bundled_skills

    bundled = [
        SkillResponse(
            skill_id=skill.skill_id,
            org_id="",
            team_id=None,
            agent_id=None,
            scope=SkillScope.BUNDLED,
            name=skill.name,
            description=skill.description,
            enabled=True,
        )
        for skill in list_bundled_skills()
    ]
    return [*(_to_skill_response(skill) for skill in skills), *bundled]


@router.put("/agents/{agent_id}/policy")
async def set_agent_skill_policy(
    agent_id: str,
    request: AgentSkillPolicyRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """设置 Agent Skill 授权策略。"""

    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        skill = await skill_db.get_by_id_required(session, request.skill_id, "skill_id")
        if skill.org_id != agent.org_id:
            raise ValueError("Skill 不属于该 Agent 的组织")
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=agent.org_id)
        policy = await agent_skill_policy_db.set_policy(
            session, agent_id=agent_id, skill_id=request.skill_id, allowed=request.allowed
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"agent_id": policy.agent_id, "skill_id": policy.skill_id, "allowed": policy.allowed}


@router.get("/agents/{agent_id}/summaries", response_model=list[SkillSummaryResponse])
async def list_agent_skill_summaries(
    agent_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[SkillSummaryResponse]:
    """列出 Agent 可用 Skill 摘要。"""

    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        await membership_db.assert_org_access(session, user_id=auth.user_id, org_id=agent.org_id)
        skills = await skill_db.list_agent_allowed_skills(session, agent_id=agent_id, org_id=agent.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [
        SkillSummaryResponse(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            scope=skill.scope,
        )
        for skill in skills
    ]


@router.get("/agents/{agent_id}/skills/{skill_id}", response_model=SkillResponse)
async def get_agent_skill(
    agent_id: str,
    skill_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> SkillResponse:
    """读取 Agent 已授权 Skill 的完整元信息。"""

    summaries = await list_agent_skill_summaries(agent_id, auth, session)
    if not any(summary.skill_id == skill_id for summary in summaries):
        raise HTTPException(status_code=403, detail="Agent 未被授权使用该 Skill")
    skill = await skill_db.get_by_id_required(session, skill_id, "skill_id")
    return _to_skill_response(skill)


def _parse_skill_markdown(content: str) -> dict[str, str]:
    """解析 SKILL.md frontmatter。"""

    frontmatter_match = re.match(r"^---\n(?P<body>.*?)\n---", content, flags=re.DOTALL)
    if frontmatter_match is None:
        raise ValueError("SKILL.md 缺少 frontmatter")
    metadata: dict[str, str] = {}
    for line in frontmatter_match.group("body").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    if not metadata.get("name"):
        raise ValueError("SKILL.md 缺少 name")
    if not metadata.get("description"):
        raise ValueError("SKILL.md 缺少 description")
    return {"name": metadata["name"], "description": metadata["description"]}


def _to_skill_response(skill: SkillModel) -> SkillResponse:
    """把 Skill ORM 模型转换为 API 响应。"""

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
