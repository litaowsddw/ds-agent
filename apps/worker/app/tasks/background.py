"""后台 Agent 服务任务。

后台 Agent 不是普通定时脚本，而是受 runtime policy 约束的系统级 Agent。
MVP 阶段先保留 Memory Compact 和 MCP Health Check 两个任务入口。
"""

from apps.worker.app.celery_app import celery_app


@celery_app.task(name="agentflow.background.memory_compact")
def memory_compact(agent_id: str, session_id: str) -> dict[str, str]:
    """压缩指定 Agent Session 的上下文历史。"""

    # agent_id 表示需要执行记忆整理的 Agent。
    target_agent_id = agent_id

    # session_id 表示需要整理的会话。
    target_session_id = session_id

    return {
        "status": "scheduled",
        "agent_id": target_agent_id,
        "session_id": target_session_id,
    }


@celery_app.task(name="agentflow.background.mcp_health_check")
def mcp_health_check(server_id: str) -> dict[str, str]:
    """检查指定 MCP Server 的健康状态。"""

    # server_id 表示需要检查的 MCP Server。
    target_server_id = server_id

    return {"status": "scheduled", "server_id": target_server_id}
