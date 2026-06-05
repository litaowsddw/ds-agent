"""Redis 结果缓存服务。

替换内存 LRU 缓存，实现多 Worker 进程间的缓存共享。
支持 TTL 过期和按类型批量失效。
"""

import hashlib
import json
from datetime import datetime
from typing import Any

from apps.api.app.core.redis import redis_client


def _compute_key(cache_type: str, key_data: dict[str, Any]) -> str:
    """计算缓存键。"""
    stable = json.dumps(
        {"type": cache_type, **key_data},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


class RedisResultCache:
    """Redis 结果缓存。

    使用 Redis Hash 存储缓存条目，支持：
    - get/put 基本缓存操作
    - TTL 过期
    - 按类型批量失效
    - 命中率统计
    """

    def __init__(self, default_ttl: int = 3600) -> None:
        # default_ttl 是默认缓存过期秒数。
        self.default_ttl = default_ttl
        # _hit_key 是命中率统计的 Redis key。
        self._hit_key = "cache:stats:hits"
        self._miss_key = "cache:stats:misses"

    async def get(self, cache_type: str, key_data: dict[str, Any]) -> dict[str, Any] | None:
        """查询缓存。命中时返回 {value, hit_count, created_at}，未命中返回 None。"""
        cache_key = f"cache:{cache_type}:{_compute_key(cache_type, key_data)}"
        raw = await redis_client.get_json(cache_key)

        if raw is not None:
            # 更新命中计数
            await redis_client._get_redis()
            r = redis_client._redis
            await r.hincrby(self._hit_key, cache_type, 1)
            raw["hit_count"] = raw.get("hit_count", 0) + 1
            return raw

        # 更新未命中计数
        await redis_client._get_redis()
        r = redis_client._redis
        await r.hincrby(self._miss_key, cache_type, 1)
        return None

    async def put(
        self,
        cache_type: str,
        key_data: dict[str, Any],
        value: Any,
        ttl: int | None = None,
    ) -> dict[str, Any]:
        """写入缓存。"""
        cache_key = f"cache:{cache_type}:{_compute_key(cache_type, key_data)}"
        entry = {
            "cache_key": cache_key,
            "cache_type": cache_type,
            "value": value,
            "hit_count": 0,
            "created_at": datetime.utcnow().isoformat(),
        }
        await redis_client.set_json(cache_key, entry, ex=ttl or self.default_ttl)
        return entry

    async def invalidate(self, cache_type: str, key_data: dict[str, Any]) -> bool:
        """主动失效单个缓存。"""
        cache_key = f"cache:{cache_type}:{_compute_key(cache_type, key_data)}"
        deleted = await redis_client.delete(cache_key)
        return deleted > 0

    async def invalidate_by_prefix(self, cache_type: str) -> int:
        """按类型批量失效缓存。"""
        pattern = f"cache:{cache_type}:*"
        keys = await redis_client.keys(pattern)
        if not keys:
            return 0
        deleted = await redis_client.delete(*keys)
        return deleted

    async def stats(self) -> dict[str, Any]:
        """返回缓存统计。"""
        r = await redis_client._get_redis()

        # 读取命中和未命中计数
        hits_data = await r.hgetall(self._hit_key)
        misses_data = await r.hgetall(self._miss_key)

        total_hits = sum(int(v) for v in hits_data.values())
        total_misses = sum(int(v) for v in misses_data.values())

        # 统计缓存键数量
        all_keys = await redis_client.keys("cache:*")
        # 过滤掉统计键
        cache_keys = [k for k in all_keys if not k.startswith("cache:stats:")]

        return {
            "size": len(cache_keys),
            "max_size": 0,
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate": (
                total_hits / (total_hits + total_misses)
                if (total_hits + total_misses) > 0
                else 0.0
            ),
            "hits_by_type": hits_data,
            "misses_by_type": misses_data,
        }


class LocalResultCache:
    """内存 LRU 结果缓存（降级方案）。

    当 Redis 不可用时自动降级使用。
    """

    def __init__(self, max_size: int = 1000) -> None:
        from collections import OrderedDict

        self.max_size = max_size
        self.cache: OrderedDict[str, dict] = OrderedDict()
        self.total_hits = 0
        self.total_misses = 0

    async def get(self, cache_type: str, key_data: dict[str, Any]) -> dict[str, Any] | None:
        """查询缓存。"""
        cache_key = _compute_key(cache_type, key_data)
        entry = self.cache.get(cache_key)
        if entry is not None:
            entry["hit_count"] = entry.get("hit_count", 0) + 1
            self.total_hits += 1
            self.cache.move_to_end(cache_key)
            return entry
        self.total_misses += 1
        return None

    async def put(
        self,
        cache_type: str,
        key_data: dict[str, Any],
        value: Any,
        ttl: int | None = None,
    ) -> dict[str, Any]:
        """写入缓存。"""
        cache_key = _compute_key(cache_type, key_data)
        entry = {
            "cache_key": cache_key,
            "cache_type": cache_type,
            "value": value,
            "hit_count": 0,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.cache[cache_key] = entry
        self.cache.move_to_end(cache_key)
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
        return entry

    async def invalidate(self, cache_type: str, key_data: dict[str, Any]) -> bool:
        """主动失效缓存。"""
        cache_key = _compute_key(cache_type, key_data)
        if cache_key in self.cache:
            del self.cache[cache_key]
            return True
        return False

    async def invalidate_by_prefix(self, cache_type: str) -> int:
        """按类型批量失效缓存。"""
        keys_to_remove = [k for k, v in self.cache.items() if v.get("cache_type") == cache_type]
        for k in keys_to_remove:
            del self.cache[k]
        return len(keys_to_remove)

    async def stats(self) -> dict[str, Any]:
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


class HybridResultCache:
    """混合结果缓存 - 优先 Redis，降级到本地。"""

    def __init__(self, default_ttl: int = 3600) -> None:
        # redis_cache 是 Redis 缓存。
        self.redis_cache = RedisResultCache(default_ttl)
        # local_cache 是本地降级缓存。
        self.local_cache = LocalResultCache()
        # _use_redis 标记是否使用 Redis。
        self._use_redis = True

    async def get(self, cache_type: str, key_data: dict[str, Any]) -> dict[str, Any] | None:
        """查询缓存。"""
        if self._use_redis:
            try:
                return await self.redis_cache.get(cache_type, key_data)
            except Exception:
                self._use_redis = False
        return await self.local_cache.get(cache_type, key_data)

    async def put(
        self,
        cache_type: str,
        key_data: dict[str, Any],
        value: Any,
        ttl: int | None = None,
    ) -> dict[str, Any]:
        """写入缓存。"""
        if self._use_redis:
            try:
                return await self.redis_cache.put(cache_type, key_data, value, ttl)
            except Exception:
                self._use_redis = False
        return await self.local_cache.put(cache_type, key_data, value, ttl)

    async def invalidate(self, cache_type: str, key_data: dict[str, Any]) -> bool:
        """主动失效缓存。"""
        if self._use_redis:
            try:
                return await self.redis_cache.invalidate(cache_type, key_data)
            except Exception:
                self._use_redis = False
        return await self.local_cache.invalidate(cache_type, key_data)

    async def invalidate_by_prefix(self, cache_type: str) -> int:
        """按类型批量失效缓存。"""
        if self._use_redis:
            try:
                return await self.redis_cache.invalidate_by_prefix(cache_type)
            except Exception:
                self._use_redis = False
        return await self.local_cache.invalidate_by_prefix(cache_type)

    async def stats(self) -> dict[str, Any]:
        """返回缓存统计。"""
        if self._use_redis:
            try:
                return await self.redis_cache.stats()
            except Exception:
                self._use_redis = False
        return await self.local_cache.stats()


# 全局结果缓存实例
result_cache = HybridResultCache()
