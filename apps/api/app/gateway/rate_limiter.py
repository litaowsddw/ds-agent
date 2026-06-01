"""Redis Lua 全局令牌桶限流器。

替换 LocalTokenBucketRateLimiter，实现多 Worker 进程间的全局限流。
使用 Redis Lua 脚本保证原子性。
"""

from apps.api.app.core.redis import redis_client


class RateLimitExceeded(RuntimeError):
    """限流超限异常。"""


# Lua 令牌桶脚本
# KEYS[1] = 限流 key
# ARGV[1] = 桶容量 capacity
# ARGV[2] = 补充速率 refill_rate（令牌/秒）
# ARGV[3] = 请求令牌数 tokens
# ARGV[4] = 当前时间戳（秒）
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

-- 读取当前桶状态
local bucket = redis.call('HMGET', key, 'tokens', 'updated_at')
local tokens = tonumber(bucket[1])
local updated_at = tonumber(bucket[2])

-- 首次使用，初始化为满桶
if tokens == nil then
    tokens = capacity
    updated_at = now
end

-- 按时间补充令牌
local elapsed = math.max(0, now - updated_at)
local refill = elapsed * refill_rate
tokens = math.min(capacity, tokens + refill)

-- 判断是否允许
local allowed = 0
if tokens >= requested then
    tokens = tokens - requested
    allowed = 1
end

-- 更新桶状态
redis.call('HMSET', key, 'tokens', tokens, 'updated_at', now)
redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) * 2)

return allowed
"""


class RedisTokenBucketRateLimiter:
    """Redis Lua 全局令牌桶限流器。

    与 LocalTokenBucketRateLimiter 接口一致，可无缝替换。
    所有操作在 Redis 服务端原子执行，多进程共享限流状态。
    """

    def __init__(self, default_capacity: int = 60, default_refill_rate: float = 1.0) -> None:
        # default_capacity 是默认桶容量。
        self.default_capacity = float(default_capacity)
        # default_refill_rate 是默认每秒补充令牌数。
        self.default_refill_rate = float(default_refill_rate)

    async def allow(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> bool:
        """尝试消费令牌，返回是否允许。"""
        import time

        final_capacity = float(capacity or self.default_capacity)
        final_refill_rate = float(refill_rate or self.default_refill_rate)
        now = time.time()

        redis_key = f"ratelimit:{key}"
        result = await redis_client.eval_script(
            script=_TOKEN_BUCKET_LUA,
            keys=[redis_key],
            args=[final_capacity, final_refill_rate, tokens, now],
        )
        return result == 1

    async def require(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> None:
        """要求必须拿到令牌，否则抛出限流异常。"""
        if not await self.allow(key=key, tokens=tokens, capacity=capacity, refill_rate=refill_rate):
            raise RateLimitExceeded(f"限流超限：{key}")


class LocalTokenBucketRateLimiter:
    """本地内存 token bucket 限流器（同步版本，向后兼容）。

    当 Redis 不可用时自动降级到本地限流。
    """

    def __init__(self, default_capacity: int = 60, default_refill_rate: float = 1.0) -> None:
        from dataclasses import dataclass
        from time import monotonic

        self.default_capacity = float(default_capacity)
        self.default_refill_rate = float(default_refill_rate)
        self.buckets: dict[str, Any] = {}

    def allow(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> bool:
        """尝试消费令牌。"""
        from time import monotonic

        bucket = self._get_bucket(key, capacity, refill_rate)
        self._refill(bucket)
        if bucket["tokens"] < tokens:
            return False
        bucket["tokens"] -= tokens
        return True

    def require(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> None:
        """要求必须拿到令牌。"""
        if not self.allow(key=key, tokens=tokens, capacity=capacity, refill_rate=refill_rate):
            raise RateLimitExceeded(f"限流超限：{key}")

    def _get_bucket(self, key: str, capacity: int | None, refill_rate: float | None) -> dict:
        from time import monotonic

        if key not in self.buckets:
            final_capacity = float(capacity or self.default_capacity)
            final_refill_rate = float(refill_rate or self.default_refill_rate)
            self.buckets[key] = {
                "capacity": final_capacity,
                "refill_rate": final_refill_rate,
                "tokens": final_capacity,
                "updated_at": monotonic(),
            }
        return self.buckets[key]

    def _refill(self, bucket: dict) -> None:
        from time import monotonic

        now = monotonic()
        elapsed = max(0.0, now - bucket["updated_at"])
        refill_tokens = elapsed * bucket["refill_rate"]
        bucket["tokens"] = min(bucket["capacity"], bucket["tokens"] + refill_tokens)
        bucket["updated_at"] = now


class HybridRateLimiter:
    """混合限流器 - 优先 Redis，降级到本地。

    当 Redis 可用时使用 Redis 全局限流，否则降级到本地限流。
    异步方法兼容 FastAPI 路由，同步方法兼容旧代码。
    """

    def __init__(self, default_capacity: int = 60, default_refill_rate: float = 1.0) -> None:
        # redis_limiter 是 Redis 全局限流器。
        self.redis_limiter = RedisTokenBucketRateLimiter(default_capacity, default_refill_rate)
        # local_limiter 是本地降级限流器。
        self.local_limiter = LocalTokenBucketRateLimiter(default_capacity, default_refill_rate)
        # _use_redis 标记是否使用 Redis。
        self._use_redis = True

    async def allow(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> bool:
        """异步尝试消费令牌。"""
        if self._use_redis:
            try:
                return await self.redis_limiter.allow(key, tokens, capacity, refill_rate)
            except Exception:
                # Redis 不可用，降级到本地
                self._use_redis = False
        return self.local_limiter.allow(key, tokens, capacity, refill_rate)

    async def require(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> None:
        """异步要求令牌。"""
        if not await self.allow(key=key, tokens=tokens, capacity=capacity, refill_rate=refill_rate):
            raise RateLimitExceeded(f"限流超限：{key}")

    def allow_sync(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> bool:
        """同步尝试消费令牌（用于旧代码兼容）。"""
        return self.local_limiter.allow(key, tokens, capacity, refill_rate)

    def require_sync(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> None:
        """同步要求令牌（用于旧代码兼容）。"""
        if not self.allow_sync(key=key, tokens=tokens, capacity=capacity, refill_rate=refill_rate):
            raise RateLimitExceeded(f"限流超限：{key}")


# 全局限流器实例
rate_limiter = HybridRateLimiter()
