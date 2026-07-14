"""LLM Gateway 测试。"""

import pytest

from apps.api.app.gateway.llm import (
    GatewayProviderError,
    LLMCallRequest,
    LLMGateway,
)
from apps.api.tests.fakes import FakeLLMProvider


@pytest.mark.asyncio
async def test_llm_gateway_records_success_log() -> None:
    """Gateway 成功调用后应该记录日志。"""

    gateway = LLMGateway(providers={"mock": FakeLLMProvider()})

    response = await gateway.generate(
        LLMCallRequest(
            provider="mock",
            model="mock-model",
            prompt="总结输入",
            metadata={"source": "test"},
        )
    )

    logs = gateway.list_logs()

    assert response.text.startswith("[fake-llm]")
    assert len(logs) == 1
    assert logs[0].status == "succeeded"
    assert logs[0].usage["prompt_tokens"] >= 1


@pytest.mark.asyncio
async def test_workflow_prompt_compiler_records_stable_prefix_hash() -> None:
    """Workflow LLM 节点应记录稳定 prefix hash。"""

    gateway = LLMGateway(providers={"mock": FakeLLMProvider()})

    first_output = await gateway.generate_from_workflow_node(
        config={
            "provider": "mock",
            "model": "mock-model",
            "system_prompt": "稳定系统提示词",
            "prompt": "第一次输入",
        },
        node_input={"workflow_input": {"text": "A"}, "upstream": {}},
    )
    second_output = await gateway.generate_from_workflow_node(
        config={
            "provider": "mock",
            "model": "mock-model",
            "system_prompt": "稳定系统提示词",
            "prompt": "第二次输入",
        },
        node_input={"workflow_input": {"text": "B"}, "upstream": {}},
    )

    logs = gateway.list_logs()

    assert first_output["prefix_hash"]
    assert first_output["prefix_hash"] == second_output["prefix_hash"]
    assert logs[0].prefix_hash == logs[1].prefix_hash


@pytest.mark.asyncio
async def test_llm_gateway_normalizes_missing_provider_error() -> None:
    """未注册 Provider 应返回标准化 Gateway 错误并记录失败日志。"""

    gateway = LLMGateway(providers={})

    with pytest.raises(GatewayProviderError):
        await gateway.generate(
            LLMCallRequest(
                provider="missing",
                model="unknown",
                prompt="hello",
            )
        )

    logs = gateway.list_logs()
    assert logs[0].status == "failed"
    assert "未注册 LLM Provider" in logs[0].error_message
