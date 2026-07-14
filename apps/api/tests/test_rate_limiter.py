"""Gateway RateLimiter 测试。"""

import pytest

from apps.api.app.gateway.llm import LLMCallRequest, LLMGateway
from apps.api.app.gateway.rate_limiter import LocalTokenBucketRateLimiter, RateLimitExceeded
from apps.api.tests.fakes import FakeLLMProvider


class AsyncLocalTokenBucketRateLimiter:
    """Adapt the real local bucket to Gateway's asynchronous limiter protocol."""

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self._local = LocalTokenBucketRateLimiter(
            default_capacity=capacity,
            default_refill_rate=refill_rate,
        )

    async def require(self, **kwargs: object) -> None:
        self._local.require(**kwargs)


def test_local_token_bucket_rejects_when_empty() -> None:
    """令牌桶耗尽后应拒绝请求。"""

    limiter = LocalTokenBucketRateLimiter(default_capacity=1, default_refill_rate=0)

    assert limiter.allow("test:key") is True
    assert limiter.allow("test:key") is False


@pytest.mark.asyncio
async def test_llm_gateway_records_rate_limit_failure() -> None:
    """Gateway 被限流时应记录失败日志。"""

    limiter = AsyncLocalTokenBucketRateLimiter(capacity=1, refill_rate=0)
    gateway = LLMGateway(providers={"mock": FakeLLMProvider()}, limiter=limiter)

    request = LLMCallRequest(provider="mock", model="mock-model", prompt="hello")
    await gateway.generate(request)

    with pytest.raises(RateLimitExceeded):
        await gateway.generate(request)

    logs = gateway.list_logs()
    assert logs[0].status == "succeeded"
    assert logs[1].status == "failed"
    assert "限流超限" in logs[1].error_message
