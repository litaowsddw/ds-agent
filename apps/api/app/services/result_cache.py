"""平台级结果缓存服务。

缓存 LLM 响应、Embedding、RAG 检索、Tool 调用和节点输出。
MVP 使用内存 LRU 缓存，后续替换为 Redis。
"""

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.api.app.domain.identity import utc_now


@dataclass(slots=True)
class CacheEntry:
    """缓存条目。"""

    # cache_key 是缓存键。
    cache_key: str

    # cache_type 是缓存类型，例如 llm、embedding、rag、tool、node。
    cache_type: str

    # value 是缓存值。
    value: Any

    # hit_count 是命中次数。
    hit_count: int = 0

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)


class ResultCache:
    """内存 LRU 结果缓存。"""

    def __init__(self, max_size: int = 1000) -> None:
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.total_hits = 0
        self.total_misses = 0

    def get(self, cache_type: str, key_data: dict[str, Any]) -> CacheEntry | None:
        """查询缓存。"""
        cache_key = self._compute_key(cache_type, key_data)
        entry = self.cache.get(cache_key)
        if entry is not None:
            entry.hit_count += 1
            self.total_hits += 1
            self.cache.move_to_end(cache_key)
            return entry
        self.total_misses += 1
        return None

    def put(
        self,
        cache_type: str,
        key_data: dict[str, Any],
        value: Any,
    ) -> CacheEntry:
        """写入缓存。"""
        cache_key = self._compute_key(cache_type, key_data)
        entry = CacheEntry(
            cache_key=cache_key,
            cache_type=cache_type,
            value=value,
        )
        self.cache[cache_key] = entry
        self.cache.move_to_end(cache_key)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
        return entry

    def invalidate(self, cache_type: str, key_data: dict[str, Any]) -> bool:
        """主动失效缓存。"""
        cache_key = self._compute_key(cache_type, key_data)
        if cache_key in self.cache:
            del self.cache[cache_key]
            return True
        return False

    def invalidate_by_prefix(self, cache_type: str) -> int:
        """按类型批量失效缓存。"""
        keys_to_remove = [k for k, v in self.cache.items() if v.cache_type == cache_type]
        for k in keys_to_remove:
            del self.cache[k]
        return len(keys_to_remove)

    def stats(self) -> dict[str, Any]:
        """返回缓存统计。"""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "hit_rate": (
                self.total_hits / (self.total_hits + self.total_misses)
                if (self.total_hits + self.total_misses) > 0
                else 0.0
            ),
        }

    def _compute_key(self, cache_type: str, key_data: dict[str, Any]) -> str:
        """计算缓存键。"""
        stable = json.dumps(
            {"type": cache_type, **key_data},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()


# result_cache 是 API 进程级默认缓存。
result_cache = ResultCache()
