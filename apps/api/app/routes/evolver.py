"""Harmes Skill Evolver API 路由。

提供 Skill 进化的管理接口：
- 触发进化
- 查看进化历史
- 审批/拒绝进化
- 查看待审批进化
- 查看运行分析
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.core.auth import AuthenticatedUser, CurrentUser

router = APIRouter()


async def _assert_evolution_access(
    db: AsyncSession, auth, org_id: str, required_role: str | None = None
) -> None:
    """进化会真实消耗 LLM 费用并改动 Skill，必须校验组织成员身份。"""
    from app.services.db.identity_db import membership_db

    try:
        await membership_db.assert_org_access(
            db, user_id=auth.user_id, org_id=org_id, required_role=required_role
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


async def _build_evolver_llm_caller(db: AsyncSession, agent, actor_user_id: str):
    """按 Agent 的 provider 配置构建真实的 Skill Evolver LLM 调用器。"""
    from app.services.chat_llm_stack import build_chat_llm_stack
    from packages.runtime.llm_caller import SkillEvolverLLMCaller

    gateway, _adapter, _chat_model = await build_chat_llm_stack(
        db,
        agent=agent,
        actor_user_id=actor_user_id,
        source="skill_evolver",
        session_id="",
    )
    return SkillEvolverLLMCaller(
        gateway=gateway,
        provider=agent.model_provider or "",
        model=agent.model_name or "",
        org_id=str(agent.org_id),
    )


class TriggerEvolutionRequest(BaseModel):
    """触发进化请求。"""
    agent_id: str
    org_id: str
    # 是否异步执行
    async_exec: bool = True


class ApproveEvolutionRequest(BaseModel):
    """审批进化请求。"""
    record_id: str
    approved: bool
    org_id: str  # 审批是高权限操作，必须显式带入组织用于成员校验


class EvolutionResponse(BaseModel):
    """进化响应。"""
    record_id: str
    agent_id: str
    action: str
    skill_name: str
    confidence: float
    status: str
    reasoning: str


@router.post("/trigger")
async def trigger_evolution(
    request: TriggerEvolutionRequest,
    auth: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
):
    """触发一次 Skill 进化循环。"""
    await _assert_evolution_access(db, auth, request.org_id)
    try:
        if request.async_exec:
            # 异步执行
            from apps.worker.app.tasks.evolver import run_evolution_cycle
            task = run_evolution_cycle.apply_async(
                kwargs={"agent_id": request.agent_id, "org_id": request.org_id},
                queue="workflow.default",
            )
            return {
                "status": "triggered",
                "task_id": task.id,
                "agent_id": request.agent_id,
            }
        else:
            # 同步执行
            from app.services.db.agent_db import agent_db
            from packages.runtime.skill_evolver import HarmesSkillEvolver

            agent = await agent_db.get_agent_required(db, request.agent_id)
            caller = await _build_evolver_llm_caller(db, agent, auth.user_id)
            evolver = HarmesSkillEvolver(llm_caller=caller)
            records = await evolver.evolve(request.agent_id, request.org_id)

            return {
                "status": "completed",
                "agent_id": request.agent_id,
                "evolution_count": len(records),
                "records": [
                    {
                        "record_id": r.record_id,
                        "action": r.action,
                        "skill_name": r.skill_name,
                        "confidence": r.confidence,
                        "status": r.status,
                        "reasoning": r.reasoning[:200],
                    }
                    for r in records
                ],
            }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"触发进化失败: {exc}")


@router.get("/analysis/{agent_id}")
async def get_run_analysis(
    agent_id: str,
    auth: CurrentUser,
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
    """获取 Agent 运行分析。"""
    await _assert_evolution_access(db, auth, org_id)
    try:
        from app.services.db.agent_db import agent_db
        from packages.runtime.skill_evolver import HarmesSkillEvolver

        agent = await agent_db.get_agent_required(db, agent_id)
        caller = await _build_evolver_llm_caller(db, agent, auth.user_id)
        evolver = HarmesSkillEvolver(llm_caller=caller)
        analysis = await evolver.analyze(agent_id, org_id)

        return {
            "agent_id": agent_id,
            "total_runs": analysis.total_runs,
            "success_rate": analysis.success_rate,
            "common_patterns": analysis.common_patterns,
            "failure_patterns": analysis.failure_patterns,
            "improvement_opportunities": analysis.improvement_opportunities,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取分析失败: {exc}")


@router.get("/history/{agent_id}")
async def get_evolution_history(
    agent_id: str,
    auth: CurrentUser,
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
    """获取 Agent 进化历史。"""
    await _assert_evolution_access(db, auth, org_id)
    try:
        from packages.runtime.skill_evolver import HarmesSkillEvolver

        evolver = HarmesSkillEvolver()
        records = evolver.get_evolution_history(agent_id)

        return {
            "agent_id": agent_id,
            "total_count": len(records),
            "records": [
                {
                    "record_id": r.record_id,
                    "action": r.action,
                    "skill_name": r.skill_name,
                    "confidence": r.confidence,
                    "status": r.status,
                    "reasoning": r.reasoning[:200],
                    "created_at": r.created_at,
                    "applied_at": r.applied_at,
                }
                for r in records
            ],
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取进化历史失败: {exc}")


@router.get("/pending")
async def get_pending_approvals(
    auth: CurrentUser,
    org_id: str = Query(...),
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """获取待审批的进化记录。"""
    await _assert_evolution_access(db, auth, org_id)
    try:
        from packages.runtime.feedback_loop import FeedbackLoop

        loop = FeedbackLoop()
        records = loop.get_pending_approvals(agent_id)

        return {
            "total_count": len(records),
            "records": [
                {
                    "record_id": r.record_id,
                    "agent_id": r.agent_id,
                    "action": r.action,
                    "skill_name": r.skill_name,
                    "confidence": r.confidence,
                    "reasoning": r.reasoning[:200],
                }
                for r in records
            ],
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取待审批列表失败: {exc}")


@router.post("/approve")
async def approve_evolution(
    request: ApproveEvolutionRequest,
    auth: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
):
    """审批或拒绝一条进化记录。"""
    try:
        from app.services.db.identity_db import membership_db

        try:
            await membership_db.assert_org_access(db, user_id=auth.user_id, org_id=request.org_id)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    try:
        from packages.runtime.feedback_loop import FeedbackLoop

        loop = FeedbackLoop()
        if request.approved:
            applied = await loop.approve_evolution(request.record_id)
            return {"status": "approved" if applied else "failed", "record_id": request.record_id}
        else:
            rejected = await loop.reject_evolution(request.record_id)
            return {"status": "rejected" if rejected else "failed", "record_id": request.record_id}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"审批操作失败: {exc}")


@router.get("/feedback-loop/{agent_id}")
async def run_feedback_loop(
    agent_id: str,
    auth: CurrentUser,
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
):
    """执行一次完整的反馈循环。"""
    await _assert_evolution_access(db, auth, org_id)
    try:
        from app.services.db.agent_db import agent_db
        from packages.runtime.feedback_loop import FeedbackLoop
        from packages.runtime.skill_evolver import HarmesSkillEvolver

        agent = await agent_db.get_agent_required(db, agent_id)
        caller = await _build_evolver_llm_caller(db, agent, auth.user_id)
        evolver = HarmesSkillEvolver(llm_caller=caller)
        loop = FeedbackLoop(evolver=evolver)
        result = await loop.run_cycle(agent_id, org_id)

        return {
            "agent_id": agent_id,
            "applied_count": result.applied_count,
            "pending_approval_count": result.pending_approval_count,
            "failed_count": result.failed_count,
            "skipped_reason": result.skipped_reason,
            "evolution_records": [
                {
                    "record_id": r.record_id,
                    "action": r.action,
                    "skill_name": r.skill_name,
                    "confidence": r.confidence,
                    "status": r.status,
                }
                for r in result.evolution_records
            ] if result.evolution_records else [],
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"反馈循环执行失败: {exc}")
