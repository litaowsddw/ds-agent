"""Gateway RateLimiter 测试。"""

import pytest

from apps.api.app.gateway.llm import LLMCallRequest, LLMGateway, MockLLMProvider
from apps.api.app.gateway.rate_limiter import LocalTokenBucketRateLimiter, RateLimitExceeded


def test_local_token_bucket_rejects_when_empty() -> None:
    """令牌桶耗尽后应拒绝请求。"""

    limiter = LocalTokenBucketRateLimiter(default_capacity=1, default_refill_rate=0)

    assert limiter.allow("test:key") is True
    assert limiter.allow("test:key") is False


def test_llm_gateway_records_rate_limit_failure() -> None:
    """Gateway 被限流时应记录失败日志。"""

    limiter = LocalTokenBucketRateLimiter(default_capacity=1, default_refill_rate=0)
    gateway = LLMGateway(providers={"mock": MockLLMProvider()}, limiter=limiter)

    request = LLMCallRequest(provider="mock", model="mock-model", prompt="hello")
    gateway.generate(request)

    with pytest.raises(RateLimitExceeded):
        gateway.generate(request)

    logs = gateway.list_logs()
    assert logs[0].status == "succeeded"
    assert logs[1].status == "failed"
    assert "限流超限" in logs[1].error_message
