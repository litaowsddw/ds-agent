"""Celery 异步任务 - SubAgent 执行任务。

将 SubAgent 执行封装为 Celery 任务，支持：
- 异步执行 SubAgent
- 执行完成后更新数据库状态
- 通过 WebSocket/SSE 推送实时状态
- Redis 缓存失效
"""

import json
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="subagent.execute",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    time_limit=300,
    soft_time_limit=270,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_subagent_task(self, run_data: dict[str, Any], org_id: str) -> dict[str, Any]:
    """异步执行 SubAgent 任务。

    参数：
        run_data: SubAgentRun 序列化数据
        org_id: 组织 ID

    返回：
        执行结果字典
    """
    run_id = run_data.get("run_id", "unknown")
    task = run_data.get("task", "")
    assigned_subagent_id = run_data.get("assigned_subagent_id", "")

    logger.info(f"开始执行 SubAgent 任务: run_id={run_id}, agent={assigned_subagent_id}")

    try:
        # 导入依赖（避免循环导入）
        from apps.api.app.database import sync_session_factory
        from apps.api.app.services.db.session_db import session_message_db
        from apps.api.app.services.db.agent_db import agent_db

        # 1. 获取 SubAgent 配置
        with sync_session_factory() as session:
            agent = agent_db.get(session, assigned_subagent_id)

        if not agent:
            return {
                "run_id": run_id,
                "status": "failed",
                "error_message": f"SubAgent 不存在: {assigned_subagent_id}",
            }

        # 2. 构建执行上下文
        agent_config = agent if isinstance(agent, dict) else {
            "agent_id": str(agent.agent_id),
            "name": agent.name,
            "description": agent.description,
            "system_prompt": getattr(agent, "system_prompt", ""),
            "model_provider": getattr(agent, "model_provider", "mock"),
            "model_name": getattr(agent, "model_name", "mock-model"),
        }

        # 3. 调用 LLM Gateway
        from apps.api.app.gateway.llm import llm_gateway, LLMCallRequest

        prompt = task
        system_prompt = agent_config.get("system_prompt", "")

        if system_prompt:
            prompt = f"[System]\n{system_prompt}\n\n[User]\n{task}"

        # 同步调用（Celery worker 中）
        import asyncio
        request = LLMCallRequest(
            provider=agent_config.get("model_provider", "mock"),
            model=agent_config.get("model_name", "mock-model"),
            prompt=prompt,
            parameters={"temperature": 0.3},
            metadata={
                "source": "subagent_execution",
                "org_id": org_id,
                "agent_id": assigned_subagent_id,
            },
        )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在异步上下文中，创建新的
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    response = pool.submit(
                        asyncio.run,
                        llm_gateway.generate(request)
                    ).result()
            else:
                response = loop.run_until_complete(llm_gateway.generate(request))
        except RuntimeError:
            response = asyncio.run(llm_gateway.generate(request))

        result_text = response.text

        # 4. 保存结果到 Session Message
        with sync_session_factory() as session:
            session_key = run_data.get("child_session_key", "")
            if session_key:
                session_message_db.create(
                    session,
                    obj_in={
                        "session_id": session_key,
                        "role": "assistant",
                        "content": result_text,
                        "meta_info": {
                            "run_id": run_id,
                            "agent_id": assigned_subagent_id,
                            "usage": response.usage,
                        },
                    },
                )

        # 5. 失效相关缓存
        try:
            from apps.api.app.core.redis import get_redis
            redis_client = get_redis()
            if redis_client:
                cache_keys = [
                    f"cache:agent:{assigned_subagent_id}:*",
                    f"cache:session:{session_key}:*",
                ]
                for pattern in cache_keys:
                    keys = redis_client.keys(pattern)
                    if keys:
                        redis_client.delete(*keys)
        except Exception as cache_err:
            logger.warning(f"缓存失效失败: {cache_err}")

        logger.info(f"SubAgent 任务完成: run_id={run_id}")

        return {
            "run_id": run_id,
            "status": "succeeded",
            "text": result_text,
            "usage": response.usage,
        }

    except Exception as exc:
        logger.error(f"SubAgent 任务失败: run_id={run_id}, error={exc}")

        # 重试
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "run_id": run_id,
                "status": "failed",
                "error_message": str(exc),
            }


@shared_task(
    name="subagent.batch_execute",
    bind=True,
    max_retries=1,
    time_limit=600,
    soft_time_limit=570,
)
def batch_execute_subagents(self, runs_data: list[dict[str, Any]], org_id: str) -> list[dict[str, Any]]:
    """批量执行多个 SubAgent 任务（按 execution_order 分组）。

    同一 execution_order 的任务并行执行，不同 order 的串行执行。
    """
    results: list[dict[str, Any]] = []

    # 按 execution_order 分组
    order_groups: dict[int, list[dict[str, Any]]] = {}
    for run_data in runs_data:
        order = run_data.get("execution_order", 0)
        if order not in order_groups:
            order_groups[order] = []
        order_groups[order].append(run_data)

    for order in sorted(order_groups.keys()):
        group = order_groups[order]

        # 同组任务并行执行
        from celery import group as celery_group
        job = celery_group([
            execute_subagent_task.s(run_data=run_data, org_id=org_id)
            for run_data in group
        ])
        group_results = job.apply_async().get(timeout=300)
        results.extend(group_results)

        # 检查是否有失败
        failed = [r for r in group_results if r.get("status") == "failed"]
        if failed:
            logger.warning(f"执行顺序 {order} 有 {len(failed)} 个任务失败")
            # 继续执行后续任务（不中断）

    return results


@shared_task(
    name="supervisor.run_cycle",
    bind=True,
    max_retries=1,
    time_limit=900,
    soft_time_limit=860,
)
def supervisor_run_cycle(
    self,
    supervisor_agent_id: str,
    org_id: str,
    user_input: str,
    max_reflection_rounds: int = 3,
) -> dict[str, Any]:
    """完整的 Supervisor 运行周期：plan → execute → reflect → (repeat)。

    参数：
        supervisor_agent_id: Supervisor Agent ID
        org_id: 组织 ID
        user_input: 用户输入
        max_reflection_rounds: 最大反思轮数

    返回：
        运行结果
    """
    logger.info(f"启动 Supervisor 运行周期: agent={supervisor_agent_id}")

    try:
        from apps.api.app.database import sync_session_factory
        from apps.api.app.services.db.agent_db import agent_db

        # 获取 Supervisor 配置
        with sync_session_factory() as session:
            agent = agent_db.get(session, supervisor_agent_id)

        if not agent:
            return {"status": "failed", "error_message": f"Supervisor Agent 不存在: {supervisor_agent_id}"}

        # 构造 LLM Caller
        from packages.runtime.llm_caller import LLMCallerAdapter
        from packages.runtime.supervisor import SupervisorAgent

        adapter = LLMCallerAdapter(
            provider=getattr(agent, "model_provider", "mock"),
            model=getattr(agent, "model_name", "mock-model"),
            org_id=org_id,
        )

        supervisor = SupervisorAgent(
            agent_id=supervisor_agent_id,
            org_id=org_id,
            model_provider=getattr(agent, "model_provider", "mock"),
            model_name=getattr(agent, "model_name", "mock-model"),
            llm_caller=adapter,
        )

        # 获取可用 SubAgent
        with sync_session_factory() as session:
            from apps.api.app.models.agent import Agent
            from sqlalchemy import select
            stmt = select(Agent).where(
                Agent.workspace_id == getattr(agent, "workspace_id", ""),
                Agent.org_id == org_id,
            )
            result = session.execute(stmt)
            subagents = result.scalars().all()

        available_subagents = [
            {
                "agent_id": str(sa.agent_id),
                "name": sa.name,
                "description": sa.description,
                "kind": getattr(sa, "kind", "USER_SUB"),
            }
            for sa in subagents
            if str(sa.agent_id) != supervisor_agent_id
        ]

        # Plan
        import asyncio
        plan = asyncio.run(supervisor.plan(user_input, available_subagents))

        # Execute
        from packages.runtime.execution_engine import SubAgentExecutionEngine
        engine = SubAgentExecutionEngine(llm_caller=adapter)

        for run in plan.subtasks:
            supervisor.spawn(run)

        execution_results = asyncio.run(
            engine.execute_sync(plan.subtasks, org_id)
        )

        # Reflect
        plan = asyncio.run(supervisor.reflect(plan))

        # 如果反思后需要后续行动
        iteration = 0
        while not plan.final_response and iteration < max_reflection_rounds:
            new_runs = [r for r in plan.subtasks if r.status.value == "pending"]
            if not new_runs:
                break

            for run in new_runs:
                supervisor.spawn(run)

            execution_results = asyncio.run(
                engine.execute_sync(new_runs, org_id)
            )

            plan = asyncio.run(supervisor.reflect(plan))
            iteration += 1

        # 聚合最终结果
        if not plan.final_response:
            final_response = supervisor.aggregate(plan)
        else:
            final_response = plan.final_response

        logger.info(f"Supervisor 运行周期完成: agent={supervisor_agent_id}, iterations={iteration}")

        return {
            "status": "succeeded",
            "final_response": final_response,
            "plan_id": plan.plan_id,
            "intent": plan.intent,
            "subtask_count": len(plan.subtasks),
            "reflection_rounds": iteration,
        }

    except Exception as exc:
        logger.error(f"Supervisor 运行周期失败: {exc}")
        return {
            "status": "failed",
            "error_message": str(exc),
        }
