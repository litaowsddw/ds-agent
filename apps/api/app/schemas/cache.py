"""缓存 API Schema。"""

from pydantic import BaseModel


class CacheStatsResponse(BaseModel):
    size: int
    max_size: int
    total_hits: int
    total_misses: int
    hit_rate: float
