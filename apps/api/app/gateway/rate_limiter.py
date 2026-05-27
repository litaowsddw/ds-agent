"""Gateway 限流器。

模块 13 先实现本地内存 token bucket，作为 Redis Lua 全局令牌桶的接口预演。
后续接入 Redis 后，只需要替换 RateLimiter 实现，Gateway 调用流程不变。
"""

from dataclasses import dataclass
from time import monotonic


class RateLimitExceeded(RuntimeError):
    """限流超限异常。"""


@dataclass(slots=True)
class TokenBucketState:
    """令牌桶状态。"""

    # capacity 是桶容量。
    capacity: float

    # refill_rate 是每秒补充令牌数。
    refill_rate: float

    # tokens 是当前剩余令牌。
    tokens: float

    # updated_at 是上次补充令牌的单调时钟时间。
    updated_at: float


class LocalTokenBucketRateLimiter:
    """本地内存 token bucket 限流器。"""

    def __init__(self, default_capacity: int = 60, default_refill_rate: float = 1.0) -> None:
        # default_capacity 是默认桶容量。
        self.default_capacity = float(default_capacity)

        # default_refill_rate 是默认每秒补充令牌数。
        self.default_refill_rate = float(default_refill_rate)

        # buckets 保存每个限流 key 的令牌桶。
        self.buckets: dict[str, TokenBucketState] = {}

    def allow(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> bool:
        """尝试消费令牌。"""

        bucket = self._get_bucket(key=key, capacity=capacity, refill_rate=refill_rate)
        self._refill(bucket=bucket)

        if bucket.tokens < tokens:
            return False

        bucket.tokens -= tokens
        return True

    def require(
        self,
        key: str,
        tokens: float = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> None:
        """要求必须拿到令牌，否则抛出限流异常。"""

        if not self.allow(key=key, tokens=tokens, capacity=capacity, refill_rate=refill_rate):
            raise RateLimitExceeded(f"限流超限：{key}")

    def _get_bucket(
        self,
        key: str,
        capacity: int | None,
        refill_rate: float | None,
    ) -> TokenBucketState:
        """读取或创建令牌桶。"""

        if key not in self.buckets:
            final_capacity = float(capacity or self.default_capacity)
            final_refill_rate = float(refill_rate or self.default_refill_rate)
            self.buckets[key] = TokenBucketState(
                capacity=final_capacity,
                refill_rate=final_refill_rate,
                tokens=final_capacity,
                updated_at=monotonic(),
            )
        return self.buckets[key]

    def _refill(self, bucket: TokenBucketState) -> None:
        """按时间补充令牌。"""

        now = monotonic()

        # elapsed 是距离上次补充的秒数。
        elapsed = max(0.0, now - bucket.updated_at)

        # refill_tokens 是本次应补充的令牌数量。
        refill_tokens = elapsed * bucket.refill_rate

        bucket.tokens = min(bucket.capacity, bucket.tokens + refill_tokens)
        bucket.updated_at = now


# rate_limiter 是 API 进程默认限流器。
rate_limiter = LocalTokenBucketRateLimiter()
