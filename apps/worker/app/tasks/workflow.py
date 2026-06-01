"""Workflow Celery 任务（数据库版本）。

Worker 任务接收发布版本 DSL 和输入，执行后将结果写入数据库。
同时更新 Redis 缓存和限流状态。
"""

import json
import time
from datetime import datetime

from apps.worker.app.celery_app import celery_app


@celery_app.task(name="agentflow.workflow.execute", bind=True, max_retries=2)
def execute_workflow(
    self,
    run_id: str,
    definition: dict,
    input_data: dict,
    org_id: str = "",
    agent_id: str = "",
) -> dict:
    """执行 Workflow DSL 并记录运行状态到数据库。

    参数：
        run_id: Workflow 运行 ID
        definition: 发布版本 DSL（不可变快照）
        input_data: 运行输入数据
        org_id: 组织 ID
        agent_id: Agent ID
    """

    # executor 是纯 Python 执行器，不依赖 API 进程状态。
    from packages.workflow.executor import WorkflowExecutor

    executor = WorkflowExecutor()
    start_time = time.time()

    try:
        # 更新运行状态为 running
        _update_run_status(run_id, "running")

        # 执行工作流
        result = executor.execute(definition=definition, input_data=input_data)

        # 记录节点运行结果
        for node_result in result.node_runs:
            _record_node_run(
                run_id=run_id,
                node_id=node_result.node_id,
                node_type=node_result.node_type,
                status=node_result.status,
                input_data=node_result.input_data,
                output_data=node_result.output_data,
                error_message=node_result.error_message,
                elapsed_ms=node_result.elapsed_ms,
            )

        # 更新运行状态
        elapsed_ms = int((time.time() - start_time) * 1000)
        final_status = result.status
        _update_run_status(
            run_id,
            final_status,
            output_data=result.output_data,
            error_message=result.error_message,
        )

        # 失效相关缓存
        _invalidate_cache("workflow_run", {"run_id": run_id})

        return {
            "status": final_status,
            "run_id": run_id,
            "elapsed_ms": elapsed_ms,
            "node_count": len(result.node_runs),
        }

    except Exception as exc:
        _update_run_status(
            run_id, "failed", error_message=f"{exc.__class__.__name__}: {exc}"
        )
        raise


def _update_run_status(
    run_id: str,
    status: str,
    output_data: dict | None = None,
    error_message: str = "",
) -> None:
    """更新 Workflow 运行状态（数据库操作）。

    Worker 进程中直接操作数据库，使用同步方式。
    """
    try:
        from app.database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            now = datetime.utcnow().isoformat()
            updates = [
                "status = :status",
                "finished_at = :finished_at" if status in ("succeeded", "failed", "cancelled") else "",
            ]
            params = {"status": status, "run_id": run_id, "finished_at": now}

            if output_data is not None:
                updates.append("output_data = :output_data")
                params["output_data"] = json.dumps(output_data, ensure_ascii=False)
            if error_message:
                updates.append("error_message = :error_message")
                params["error_message"] = error_message[:2000]

            set_clause = ", ".join(s for s in updates if s)
            stmt = text(f"UPDATE workflow_runs SET {set_clause} WHERE run_id = :run_id")
            conn.execute(stmt, params)
            conn.commit()
    except Exception:
        # 数据库更新失败不应影响任务返回
        pass


def _record_node_run(
    run_id: str,
    node_id: str,
    node_type: str,
    status: str,
    input_data: dict,
    output_data: dict,
    error_message: str,
    elapsed_ms: int,
) -> None:
    """记录节点运行结果到数据库。"""
    try:
        from app.database import engine
        from app.domain.identity import new_id
        from sqlalchemy import text

        with engine.connect() as conn:
            now = datetime.utcnow().isoformat()
            stmt = text("""
                INSERT INTO node_runs (node_run_id, run_id, node_id, node_type, status,
                    input_data, output_data, error_message, elapsed_ms, started_at, finished_at)
                VALUES (:id, :run_id, :node_id, :node_type, :status,
                    :input_data, :output_data, :error_message, :elapsed_ms, :started_at, :finished_at)
            """)
            conn.execute(stmt, {
                "id": new_id("nr"),
                "run_id": run_id,
                "node_id": node_id,
                "node_type": node_type,
                "status": status,
                "input_data": json.dumps(input_data, ensure_ascii=False),
                "output_data": json.dumps(output_data, ensure_ascii=False),
                "error_message": error_message[:2000],
                "elapsed_ms": elapsed_ms,
                "started_at": now,
                "finished_at": now if status in ("succeeded", "failed") else None,
            })
            conn.commit()
    except Exception:
        pass


def _invalidate_cache(cache_type: str, key_data: dict) -> None:
    """失效 Redis 缓存。"""
    try:
        import redis
        r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
        # 简单删除匹配的缓存键
        pattern = f"cache:{cache_type}:*"
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception:
        pass
