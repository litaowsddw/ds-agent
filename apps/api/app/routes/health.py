"""健康检查接口。

/health      — 进程级 liveness（容器探活）
/health/ready — 依赖级 readiness（MySQL/Redis/Milvus 连通性），供部署与负载均衡使用
"""

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter()


@router.get("")
async def health_check() -> dict[str, str]:
    """返回 API 服务健康状态。"""

    # status 表示当前 API 进程是否可接收请求。
    status = "ok"

    # service 表示健康检查来源服务，方便多服务部署时定位。
    service = "api"

    return {"status": status, "service": service}


@router.get("/ready")
async def readiness_check() -> dict[str, object]:
    """依赖级就绪检查：数据库/Redis（可选 Milvus）连通性。"""

    dependencies: dict[str, str] = {}

    # MySQL 连通性
    try:
        from app.database import async_engine

        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        dependencies["mysql"] = "ok"
    except Exception as exc:
        dependencies["mysql"] = f"error: {type(exc).__name__}"

    # Redis 连通性
    try:
        from app.core.redis import redis_client

        dependencies["redis"] = "ok" if await redis_client.ping() else "error: ping failed"
    except Exception as exc:
        dependencies["redis"] = f"error: {type(exc).__name__}"

    healthy = all(value == "ok" for value in dependencies.values())
    return {"status": "ok" if healthy else "degraded", "service": "api", "dependencies": dependencies}
