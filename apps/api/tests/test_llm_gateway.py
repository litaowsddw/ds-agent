"""LLM Gateway 测试。"""

import pytest

from apps.api.app.gateway.llm import GatewayProviderError, LLMCallRequest, LLMGateway, MockLLMProvider


def test_llm_gateway_records_success_log() -> None:
    """Gateway 成功调用后应该记录日志。"""

    gateway = LLMGateway(providers={"mock": MockLLMProvider()})

    response = gateway.generate(
        LLMCallRequest(
            provider="mock",
            model="mock-model",
            prompt="总结输入",
            metadata={"source": "test"},
        )
    )

    logs = gateway.list_logs()

    assert response.text.startswith("[mock-llm]")
    assert len(logs) == 1
    assert logs[0].status == "succeeded"
    assert logs[0].usage["prompt_tokens"] >= 1


def test_llm_gateway_normalizes_missing_provider_error() -> None:
    """未注册 Provider 应返回标准化 Gateway 错误并记录失败日志。"""

    gateway = LLMGateway(providers={})

    with pytest.raises(GatewayProviderError):
        gateway.generate(
            LLMCallRequest(
                provider="missing",
                model="unknown",
                prompt="hello",
            )
        )

    logs = gateway.list_logs()
    assert logs[0].status == "failed"
    assert "未注册 LLM Provider" in logs[0].error_message

