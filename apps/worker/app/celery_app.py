"""Celery 应用配置（Redis Broker 版本）。

Worker 是 AgentFlow 高并发异步执行的基础。
支持 Redis Broker/Result Backend、任务路由、超时控制。
"""

import os

try:
    from celery import Celery
except ModuleNotFoundError:
    Celery = None


class LocalTask:
    """本地 Celery 缺失时的任务包装器。"""

    def __init__(self, func, *, name: str, bind: bool = False):
        # func 是被装饰的原始任务函数。
        self.func = func
        self.name = name
        self.bind = bind

    def run(self, *args, **kwargs):
        """Execute the task using the same bound-task convention as Celery."""
        if self.bind:
            return self.func(self, *args, **kwargs)
        return self.func(*args, **kwargs)

    def delay(self, *args, **kwargs):
        """模拟 Celery delay，立即执行函数。"""
        result = self.run(*args, **kwargs)

        class LocalResult:
            """本地同步执行结果。"""
            id = "local-task"
            value = result

        return LocalResult()

    def apply_async(self, *args, **kwargs):
        """模拟 apply_async，与 delay 行为一致。"""
        return self.delay(*args, **kwargs)


class LocalCelery:
    """Celery 缺失时的最小应用替身。"""

    def __init__(self) -> None:
        self.conf = type("LocalCeleryConfig", (), {})()

    def task(self, name: str | None = None, bind: bool = False, **_options):
        """模拟 Celery task 装饰器。"""
        def decorator(func):
            return LocalTask(func, name=name or func.__name__, bind=bind)

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

    # Redis 连接池配置 - 提高性能
    celery_app.conf.broker_transport_options = {
        "master_name": "agentflow-master",
        "visibility_timeout": 3600,
    }
    celery_app.conf.redis_backend_health_check_interval = 10

# task_routes 明确任务进入哪个队列
celery_app.conf.task_routes = {
    "agentflow.smoke.ping": {"queue": "workflow.default"},
    "agentflow.background.memory_compact": {"queue": "background.memory"},
    "agentflow.background.mcp_health_check": {"queue": "background.mcp"},
    "agentflow.workflow.execute": {"queue": "workflow.default"},
}

# 任务超时配置
celery_app.conf.task_time_limit = 300
celery_app.conf.task_soft_time_limit = 240

# 序列化配置
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]

# 任务结果过期时间
celery_app.conf.result_expires = 3600

# 并发控制
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.worker_max_tasks_per_child = 1000
