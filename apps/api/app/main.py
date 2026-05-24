"""AgentFlow API 服务入口。

本文件只负责组装 FastAPI 应用和注册路由，具体业务逻辑放在 service、runtime、
gateway 等模块中，避免入口文件变成难以维护的“大杂烩”。
"""

from fastapi import FastAPI

from apps.api.app.routes.agents import router as agents_router
from apps.api.app.routes.context import router as context_router
from apps.api.app.routes.gateway import router as gateway_router
from apps.api.app.routes.identity import router as identity_router
from apps.api.app.routes.mcp import router as mcp_router
from apps.api.app.routes.health import router as health_router
from apps.api.app.routes.runtime import router as runtime_router
from apps.api.app.routes.sessions import router as sessions_router
from apps.api.app.routes.skills import router as skills_router
from apps.api.app.routes.workflows import router as workflows_router
from apps.api.app.routes.workflow_runs import router as workflow_runs_router


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。

    返回值：
        FastAPI: 已注册基础路由的应用对象。
    """

    # 应用名称：用于 OpenAPI 文档和服务发现时识别当前服务。
    app_title = "AgentFlow API"

    # 应用版本：和项目发布版本保持一致，便于排查线上接口差异。
    app_version = "0.1.0"

    app = FastAPI(title=app_title, version=app_version)
    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(identity_router, prefix="/identity", tags=["identity"])
    app.include_router(agents_router, prefix="/agents", tags=["agents"])
    app.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
    app.include_router(skills_router, prefix="/skills", tags=["skills"])
    app.include_router(mcp_router, prefix="/mcp", tags=["mcp"])
    app.include_router(workflows_router, prefix="/workflows", tags=["workflows"])
    app.include_router(workflow_runs_router, prefix="/workflow-runs", tags=["workflow-runs"])
    app.include_router(gateway_router, prefix="/gateway", tags=["gateway"])
    app.include_router(context_router, prefix="/context", tags=["context"])
    app.include_router(runtime_router, prefix="/runtime", tags=["runtime"])
    return app


# FastAPI 运行时直接读取的应用对象。
app = create_app()
