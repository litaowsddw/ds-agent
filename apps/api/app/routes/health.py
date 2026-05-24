"""健康检查接口。

健康检查是部署、监控和本地联调的第一入口。MVP 阶段先返回进程可用状态，
后续会扩展数据库、Redis、Celery、MCP Server 等依赖检查。
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health_check() -> dict[str, str]:
    """返回 API 服务健康状态。"""

    # status 表示当前 API 进程是否可接收请求。
    status = "ok"

    # service 表示健康检查来源服务，方便多服务部署时定位。
    service = "api"

    return {"status": status, "service": service}

