"""Worker 冒烟测试任务。"""

from apps.worker.app.celery_app import celery_app


@celery_app.task(name="agentflow.smoke.ping")
def ping() -> dict[str, str]:
    """返回 Worker 可用状态。"""

    # status 表示 Celery Worker 已成功执行任务。
    status = "ok"

    # service 表示任务来源服务。
    service = "worker"

    return {"status": status, "service": service}
