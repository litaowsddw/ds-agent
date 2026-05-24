"""Celery 应用配置。

Worker 是 AgentFlow 高并发异步执行的基础。MVP 阶段先提供 smoke task，
后续逐步接入 Workflow Executor、Background Agent、RAG 索引和缓存维护任务。
"""

import os

try:
    from celery import Celery
except ModuleNotFoundError:
    Celery = None


class LocalTask:
    """本地 Celery 缺失时的任务包装器。

    该类只用于开发和测试环境，让任务函数可以通过 `.run()` 直接执行。
    生产环境安装 Celery 后不会使用它。
    """

    def __init__(self, func):
        # func 是被装饰的原始任务函数。
        self.func = func

        # run 模拟 Celery Task 的直接执行入口。
        self.run = func

    def delay(self, *args, **kwargs):
        """模拟 Celery delay，立即执行函数并返回最小结果对象。"""

        # result 是同步执行结果。
        result = self.func(*args, **kwargs)

        class LocalResult:
            """本地同步执行结果。"""

            # id 是模拟任务 ID。
            id = "local-task"

            # value 保存同步执行结果。
            value = result

        return LocalResult()


class LocalCelery:
    """Celery 缺失时的最小应用替身。"""

    def __init__(self) -> None:
        # conf 保存任务配置，兼容真实 Celery 的 conf 属性。
        self.conf = type("LocalCeleryConfig", (), {})()

    def task(self, name: str):
        """模拟 Celery task 装饰器。"""

        # task_name 是任务名称，MVP fallback 中只保留给调试阅读。
        task_name = name

        def decorator(func):
            local_task = LocalTask(func)
            local_task.name = task_name
            return local_task

        return decorator


# broker_url 是 Celery 任务投递地址，默认使用 Redis 的 1 号库。
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

# result_backend 是 Celery 任务结果存储地址，默认使用 Redis 的 2 号库。
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

if Celery is None:
    celery_app = LocalCelery()
else:
    celery_app = Celery(
        "agentflow",
        broker=broker_url,
        backend=result_backend,
        include=[
            "apps.worker.app.tasks.smoke",
            "apps.worker.app.tasks.background",
            "apps.worker.app.tasks.workflow",
        ],
    )

# task_routes 明确任务进入哪个队列，避免所有后台任务挤在 default 队列里。
celery_app.conf.task_routes = {
    "agentflow.smoke.ping": {"queue": "workflow.default"},
    "agentflow.background.memory_compact": {"queue": "background.memory"},
    "agentflow.background.mcp_health_check": {"queue": "background.mcp"},
    "agentflow.workflow.execute": {"queue": "workflow.default"},
}

# task_time_limit 是硬超时，防止异常任务永久占用 Worker。
celery_app.conf.task_time_limit = 300

# task_soft_time_limit 是软超时，任务可以捕获该异常并做清理。
celery_app.conf.task_soft_time_limit = 240
