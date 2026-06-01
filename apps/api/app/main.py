"""AgentFlow API 服务入口。

本文件只负责组装 FastAPI 应用和注册路由，具体业务逻辑放在 service、runtime、
gateway 等模块中，避免入口文件变成难以维护的"大杂烩"。

启动时自动初始化数据库连接和 Redis 健康检查。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.telemetry import TracingMiddleware, init_otel
from app.core.logging import RequestLoggingMiddleware, setup_logging

from apps.api.app.routes.agents import router as agents_router
from apps.api.app.routes.background_agents import router as background_agents_router
from apps.api.app.routes.cache import router as cache_router
from apps.api.app.routes.context import router as context_router
from apps.api.app.routes.gateway import router as gateway_router
from apps.api.app.routes.health import router as health_router
from apps.api.app.routes.identity import router as identity_router
from apps.api.app.routes.knowledge import router as knowledge_router
from apps.api.app.routes.mcp import router as mcp_router
from apps.api.app.routes.memory import router as memory_router
from apps.api.app.routes.model_providers import router as model_providers_router
from apps.api.app.routes.runtime import router as runtime_router
from apps.api.app.routes.sessions import router as sessions_router
from apps.api.app.routes.skills import router as skills_router
from apps.api.app.routes.workflow_runs import router as workflow_runs_router
from apps.api.app.routes.workflows import router as workflows_router
from packages.a2a.routes import router as a2a_router
from apps.api.app.routes.ws import router as ws_router
from apps.api.app.routes.chat import router as chat_router
from apps.api.app.routes.evolver import router as evolver_router
from apps.api.app.routes.rbac import router as rbac_router
from apps.api.app.routes.metrics import router as metrics_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 启动和关闭时的操作。"""
    # ── 启动 ──
    import logging

    # 初始化结构化日志
    setup_logging()
    logger = logging.getLogger("agentflow")

    # 初始化 OpenTelemetry
    init_otel()
    logger.info("OpenTelemetry 初始化完成")

    # 初始化数据库表
    try:
        from app.database import init_db
        await init_db()
        logger.info("数据库初始化完成")
    except Exception as exc:
        logger.warning(f"数据库初始化失败（非致命）：{exc}")

    # Redis 健康检查
    try:
        from app.core.redis import redis_client
        is_healthy = await redis_client.ping()
        if is_healthy:
            logger.info("Redis 连接正常")
        else:
            logger.warning("Redis 连接异常，降级到本地缓存/限流")
    except Exception:
        logger.warning("Redis 不可用，降级到本地缓存/限流")

    logger.info("AgentFlow API 启动完成")

    yield

    # ── 关闭 ──
    logger.info("AgentFlow API 正在关闭...")
    try:
        from app.database import engine
        await engine.dispose()
        logger.info("数据库连接池已关闭")
    except Exception:
        pass


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""

    app_title = "AgentFlow API"
    app_version = "0.2.0"

    app = FastAPI(title=app_title, version=app_version, lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(identity_router, prefix="/identity", tags=["identity"])
    app.include_router(agents_router, prefix="/agents", tags=["agents"])
    app.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
    app.include_router(skills_router, prefix="/skills", tags=["skills"])
    app.include_router(mcp_router, prefix="/mcp", tags=["mcp"])
    app.include_router(memory_router, prefix="/memory", tags=["memory"])
    app.include_router(workflows_router, prefix="/workflows", tags=["workflows"])
    app.include_router(workflow_runs_router, prefix="/workflow-runs", tags=["workflow-runs"])
    app.include_router(gateway_router, prefix="/gateway", tags=["gateway"])
    app.include_router(model_providers_router, prefix="/model-providers", tags=["model-providers"])
    app.include_router(context_router, prefix="/context", tags=["context"])
    app.include_router(runtime_router, prefix="/runtime", tags=["runtime"])
    app.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
    app.include_router(cache_router, prefix="/cache", tags=["cache"])
    app.include_router(
        background_agents_router,
        prefix="/background-agents",
        tags=["background-agents"],
    )
    app.include_router(a2a_router, prefix="/a2a", tags=["a2a"])
    # WebSocket / SSE 实时事件推送
    app.include_router(ws_router, prefix="/ws", tags=["websocket"])
    # Chat 路由（Supervisor Agent 对话）
    app.include_router(chat_router, prefix="/chat", tags=["chat"])
    # Harmes Skill Evolver
    app.include_router(evolver_router, prefix="/evolver", tags=["evolver"])
    # RBAC 权限管理
    app.include_router(rbac_router, prefix="/rbac", tags=["rbac"])
    # Prometheus 指标
    app.include_router(metrics_router, prefix="/metrics", tags=["metrics"])

    return app


# FastAPI 运行时直接读取的应用对象。
app = create_app()
