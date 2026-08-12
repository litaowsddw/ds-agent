"""Skill evaluation and evolution candidate API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.schemas.skill_evaluation import (
    SkillEvaluationDecisionRequest,
    SkillEvaluationResponse,
    SkillEvaluationSuggestRequest,
    SkillEvaluationUpdateRequest,
)
from app.services.db.agent_db import agent_db
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import skill_db, skill_evaluation_db
from app.core.auth import AuthenticatedUser, resolve_actor, CurrentUser

router = APIRouter()


@router.get("", response_model=list[SkillEvaluationResponse])
async def list_skill_evaluations(
    auth: AuthenticatedUser,
    org_id: str = Query(description="组织 ID"),
    agent_id: str | None = Query(default=None, description="Agent ID"),
    skill_id: str | None = Query(default=None, description="Skill ID"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> list[SkillEvaluationResponse]:
    try:
        await membership_db.assert_org_access(session, user_id=auth.user_id, org_id=org_id)
        evaluations = await skill_evaluation_db.list_org_evaluations(
            session,
            org_id=org_id,
            agent_id=agent_id,
            skill_id=skill_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [_to_response(item) for item in evaluations]


@router.put("/{evaluation_id}/evaluate", response_model=SkillEvaluationResponse)
async def evaluate_skill_use(
    evaluation_id: str,
    request: SkillEvaluationUpdateRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> SkillEvaluationResponse:
    try:
        evaluation = await skill_evaluation_db.get_by_id_required(session, evaluation_id, "evaluation_id")
        await membership_db.assert_org_access(session, user_id=resolve_actor(auth, request.actor_user_id), org_id=evaluation.org_id)
        evaluation = await skill_evaluation_db.update_evaluation(
            session,
            evaluation_id,
            score=request.score,
            failure_reason=request.failure_reason,
            improvement_suggestion=request.improvement_suggestion,
            status="evaluated",
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(evaluation)


@router.post("/{evaluation_id}/suggest", response_model=SkillEvaluationResponse)
async def suggest_skill_patch(
    evaluation_id: str,
    request: SkillEvaluationSuggestRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> SkillEvaluationResponse:
    """Generate a conservative candidate patch from one evaluation record."""

    try:
        evaluation = await skill_evaluation_db.get_by_id_required(session, evaluation_id, "evaluation_id")
        await membership_db.assert_org_access(session, user_id=resolve_actor(auth, request.actor_user_id), org_id=evaluation.org_id)
        skill = await skill_db.get_by_id_required(session, evaluation.skill_id, "skill_id")
        suggestion = _build_candidate_patch(
            skill_name=skill.name,
            user_input=evaluation.user_input,
            assistant_output=evaluation.assistant_output,
            failure_reason=evaluation.failure_reason,
            improvement_suggestion=evaluation.improvement_suggestion,
        )
        evaluation = await skill_evaluation_db.update_evaluation(
            session,
            evaluation_id,
            proposed_skill_patch=suggestion,
            status="evaluated" if evaluation.status == "pending" else evaluation.status,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(evaluation)


@router.put("/{evaluation_id}/decision", response_model=SkillEvaluationResponse)
async def decide_skill_patch(
    evaluation_id: str,
    request: SkillEvaluationDecisionRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> SkillEvaluationResponse:
    try:
        evaluation = await skill_evaluation_db.get_by_id_required(session, evaluation_id, "evaluation_id")
        await membership_db.assert_org_access(session, user_id=resolve_actor(auth, request.actor_user_id), org_id=evaluation.org_id)
        evaluation = await skill_evaluation_db.update_evaluation(
            session,
            evaluation_id,
            status=request.decision,
            applied=request.decision == "applied",
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(evaluation)


def _build_candidate_patch(
    *,
    skill_name: str,
    user_input: str,
    assistant_output: str,
    failure_reason: str,
    improvement_suggestion: str,
) -> str:
    return "\n".join(
        [
            "## Evaluation-Derived Improvement Candidate",
            f"- Skill: {skill_name}",
            f"- Observed request: {_compact(user_input, 500)}",
            f"- Observed answer: {_compact(assistant_output, 500)}",
            f"- Failure reason: {failure_reason or 'No explicit failure reason recorded.'}",
            f"- Proposed improvement: {improvement_suggestion or 'Review whether the skill workflow needs clearer trigger, input parsing, or output format guidance.'}",
            "",
            "Apply this candidate manually after reviewing whether it generalizes beyond this single run.",
        ]
    )


def _compact(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 12].rstrip() + " [truncated]"


def _to_response(evaluation: object) -> SkillEvaluationResponse:
    created_at = getattr(evaluation, "created_at", None)
    return SkillEvaluationResponse(
        evaluation_id=str(evaluation.evaluation_id),
        org_id=str(evaluation.org_id),
        agent_id=str(evaluation.agent_id),
        skill_id=str(evaluation.skill_id),
        session_id=evaluation.session_id,
        user_input=evaluation.user_input or "",
        assistant_output=evaluation.assistant_output or "",
        status=evaluation.status or "pending",
        score=evaluation.score,
        failure_reason=evaluation.failure_reason or "",
        improvement_suggestion=evaluation.improvement_suggestion or "",
        proposed_skill_patch=evaluation.proposed_skill_patch or "",
        applied=bool(evaluation.applied),
        created_by=evaluation.created_by or "",
        created_at=str(created_at) if created_at else "",
    )
