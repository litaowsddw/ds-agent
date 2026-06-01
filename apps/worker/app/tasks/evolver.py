"""Celery 异步任务 - Harmes Skill Evolver 定时进化。

提供：
- 单个 Agent 进化任务
- 批量 Agent 进化任务（Celery Beat 调度）
- 反馈循环任务
"""

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="evolver.run_cycle",
    bind=True,
    max_retries=1,
    time_limit=600,
    soft_time_limit=570,
)
def run_evolution_cycle(self, agent_id: str, org_id: str) -> dict[str, Any]:
    """执行单个 Agent 的进化循环。

    参数：
        agent_id: Agent ID
        org_id: 组织 ID

    返回：
        进化结果字典
    """
    logger.info(f"启动 Skill 进化循环: agent={agent_id}")

    try:
        import asyncio
        from packages.runtime.skill_evolver import HarmesSkillEvolver
        from packages.runtime.llm_caller import SkillEvolverLLMCaller

        caller = SkillEvolverLLMCaller(org_id=org_id)
        evolver = HarmesSkillEvolver(llm_caller=caller)

        records = asyncio.run(evolver.evolve(agent_id, org_id))

        # 应用高置信度进化
        applied = 0
        for record in records:
            if record.confidence >= 0.8 and record.status.value == "succeeded":
                success = asyncio.run(evolver.apply_evolution(record))
                if success:
                    applied += 1

        logger.info(f"Skill 进化完成: agent={agent_id}, total={len(records)}, applied={applied}")

        return {
            "status": "succeeded",
            "agent_id": agent_id,
            "total_evolutions": len(records),
            "applied": applied,
            "records": [
                {
                    "record_id": r.record_id,
                    "action": r.action,
                    "skill_name": r.skill_name,
                    "confidence": r.confidence,
                    "status": r.status,
                }
                for r in records
            ],
        }

    except Exception as exc:
        logger.error(f"Skill 进化失败: agent={agent_id}, error={exc}")
        return {"status": "failed", "agent_id": agent_id, "error_message": str(exc)}


@shared_task(
    name="evolver.batch_run",
    bind=True,
    max_retries=1,
    time_limit=1800,
    soft_time_limit=1750,
)
def batch_evolution(self, org_id: str) -> dict[str, Any]:
    """对组织内所有 Agent 执行批量进化。

    由 Celery Beat 定时触发，通常每天执行一次。

    参数：
        org_id: 组织 ID

    返回：
        批量进化结果
    """
    logger.info(f"启动批量 Skill 进化: org={org_id}")

    try:
        from apps.api.app.database import sync_session_factory
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.models.agent import Agent
        from sqlalchemy import select

        # 获取组织内所有 Agent
        with sync_session_factory() as session:
            stmt = select(Agent).where(Agent.org_id == org_id)
            result = session.execute(stmt)
            agents = result.scalars().all()

        # 对每个 Agent 执行进化
        total = len(agents)
        succeeded = 0
        failed = 0

        for agent in agents:
            try:
                run_evolution_cycle.delay(
                    agent_id=str(agent.agent_id),
                    org_id=org_id,
                )
                succeeded += 1
            except Exception:
                failed += 1

        logger.info(f"批量 Skill 进化完成: org={org_id}, total={total}, dispatched={succeeded}, failed={failed}")

        return {
            "status": "succeeded",
            "org_id": org_id,
            "total_agents": total,
            "dispatched": succeeded,
            "failed": failed,
        }

    except Exception as exc:
        logger.error(f"批量 Skill 进化失败: org={org_id}, error={exc}")
        return {"status": "failed", "org_id": org_id, "error_message": str(exc)}


@shared_task(
    name="evolver.feedback_loop",
    bind=True,
    max_retries=1,
    time_limit=900,
    soft_time_limit=860,
)
def run_feedback_loop(self, agent_id: str, org_id: str) -> dict[str, Any]:
    """执行完整的反馈循环。

    参数：
        agent_id: Agent ID
        org_id: 组织 ID

    返回：
        反馈循环结果
    """
    logger.info(f"启动反馈循环: agent={agent_id}")

    try:
        import asyncio
        from packages.runtime.feedback_loop import FeedbackLoop, FeedbackLoopConfig
        from packages.runtime.skill_evolver import HarmesSkillEvolver
        from packages.runtime.llm_caller import SkillEvolverLLMCaller

        caller = SkillEvolverLLMCaller(org_id=org_id)
        evolver = HarmesSkillEvolver(llm_caller=caller)
        loop = FeedbackLoop(
            evolver=evolver,
            config=FeedbackLoopConfig(evolution_policy="semi_auto"),
        )

        result = asyncio.run(loop.run_cycle(agent_id, org_id))

        logger.info(
            f"反馈循环完成: agent={agent_id}, "
            f"applied={result.applied_count}, "
            f"pending={result.pending_approval_count}, "
            f"failed={result.failed_count}"
        )

        return {
            "status": "succeeded",
            "agent_id": agent_id,
            "applied_count": result.applied_count,
            "pending_approval_count": result.pending_approval_count,
            "failed_count": result.failed_count,
            "skipped_reason": result.skipped_reason,
        }

    except Exception as exc:
        logger.error(f"反馈循环失败: agent={agent_id}, error={exc}")
        return {"status": "failed", "agent_id": agent_id, "error_message": str(exc)}
