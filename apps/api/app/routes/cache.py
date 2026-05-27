"""缓存管理 API。"""

from fastapi import APIRouter

from apps.api.app.schemas.cache import CacheStatsResponse
from apps.api.app.services.result_cache import result_cache

router = APIRouter()


@router.get("/stats", response_model=CacheStatsResponse)
async def cache_stats() -> CacheStatsResponse:
    """查看缓存统计。"""
    stats = result_cache.stats()
    return CacheStatsResponse(**stats)


@router.post("/invalidate/{cache_type}")
async def invalidate_cache(cache_type: str) -> dict[str, int]:
    """按类型批量失效缓存。"""
    removed = result_cache.invalidate_by_prefix(cache_type)
    return {"removed": removed}
