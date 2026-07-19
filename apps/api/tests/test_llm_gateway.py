"""LLM Gateway 测试。"""

import pytest

from apps.api.app.gateway.llm import (
    GatewayProviderError,
    LLMCallRequest,
    LLMGateway,
    LLMStreamChunk,
    OpenAICompatibleProvider,
)
from apps.api.tests.fakes import FakeLLMProvider


class StreamingFakeLLMProvider(FakeLLMProvider):
    """Provider double that emits text chunks followed by terminal usage."""

    def stream_generate(self, request: LLMCallRequest):
        yield LLMStreamChunk(text="A")
        yield LLMStreamChunk(text="B")
        yield LLMStreamChunk(
            usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        )


class UnavailableUsageStreamingProvider(FakeLLMProvider):
    """Provider double that completes a text stream without usage metadata."""

    def stream_generate(self, request: LLMCallRequest):
        yield LLMStreamChunk(text="fresh")


class FailingStreamingProvider(FakeLLMProvider):
    """Provider double that raises while the Gateway consumes its stream."""

    def stream_generate(self, request: LLMCallRequest):
        raise RuntimeError("stream provider failed")
        yield LLMStreamChunk(text="unreachable")


class ClosableStreamingProvider(FakeLLMProvider):
    """Provider double that records whether Gateway closes an early-exited stream."""

    def __init__(self) -> None:
        self.closed = False

    def stream_generate(self, request: LLMCallRequest):
        try:
            yield LLMStreamChunk(text="partial")
            yield LLMStreamChunk(text="unreachable")
        finally:
            self.closed = True


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
async def test_stream_workflow_node_reports_chunks_and_returns_existing_shape() -> None:
    """Workflow streams text callbacks before exposing terminal provider usage."""

    gateway = LLMGateway(providers={"mock": StreamingFakeLLMProvider()})
    seen: list[str] = []
    usage_seen_during_callbacks = []

    async def on_text(text: str) -> None:
        seen.append(text)
        usage_seen_during_callbacks.append(gateway.last_normalized_usage)

    result = await gateway.stream_generate_from_workflow_node(
        config={
            "provider": "mock",
            "model": "mock-model",
            "system_prompt": "stream system prompt",
            "prompt": "stream input",
        },
        node_input={"workflow_input": {"text": "hi"}, "upstream": {}},
        on_text=on_text,
    )

    assert seen == ["A", "B"]
    assert usage_seen_during_callbacks == [None, None]
    assert result["text"] == "AB"
    assert result["usage"]["prompt_tokens"] == 10
    assert gateway.last_normalized_usage is not None
    assert gateway.last_normalized_usage.input_tokens == 10


@pytest.mark.asyncio
async def test_stream_workflow_node_clears_prior_usage_before_callback_and_when_unavailable() -> None:
    """A usage-less stream must not expose facts from a prior completed call."""

    gateway = LLMGateway(providers={"mock": UnavailableUsageStreamingProvider()})
    await gateway.generate(
        LLMCallRequest(provider="mock", model="mock-model", prompt="seed prior usage")
    )
    seen_usage: list[tuple[dict[str, object], object]] = []

    async def on_text(text: str) -> None:
        seen_usage.append((dict(gateway.last_raw_usage), gateway.last_normalized_usage))

    result = await gateway.stream_generate_from_workflow_node(
        config={"provider": "mock", "model": "mock-model", "prompt": "stream input"},
        node_input={"workflow_input": {"text": "hi"}, "upstream": {}},
        on_text=on_text,
    )

    assert seen_usage == [({}, None)]
    assert result["usage"] == {}
    assert gateway.last_raw_usage == {}
    assert gateway.last_normalized_usage is None


@pytest.mark.asyncio
async def test_stream_generate_clears_prior_usage_after_provider_error() -> None:
    """A failed stream must not retain usage from a previously completed call."""

    gateway = LLMGateway(providers={"mock": FailingStreamingProvider()})
    await gateway.generate(
        LLMCallRequest(provider="mock", model="mock-model", prompt="seed prior usage")
    )

    with pytest.raises(GatewayProviderError, match="stream provider failed"):
        async for _ in gateway.stream_generate(
            LLMCallRequest(provider="mock", model="mock-model", prompt="failing stream")
        ):
            pass

    assert gateway.last_raw_usage == {}
    assert gateway.last_normalized_usage is None


@pytest.mark.asyncio
async def test_stream_generate_clears_prior_usage_and_closes_provider_stream_on_cancellation() -> None:
    """Early consumer exit clears stale usage and closes the provider generator."""

    provider = ClosableStreamingProvider()
    gateway = LLMGateway(providers={"mock": provider})
    await gateway.generate(
        LLMCallRequest(provider="mock", model="mock-model", prompt="seed prior usage")
    )

    stream = gateway.stream_generate(
        LLMCallRequest(provider="mock", model="mock-model", prompt="partial stream")
    )
    assert await anext(stream) == "partial"
    await stream.aclose()

    assert provider.closed is True
    assert gateway.last_raw_usage == {}
    assert gateway.last_normalized_usage is None


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


def test_openai_provider_uses_native_messages_when_supplied() -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid",
        api_key="test-key",
        provider_key="test",
    )
    request = LLMCallRequest(
        provider="test",
        model="test-model",
        prompt="diagnostic serialization only",
        messages=[
            {"role": "system", "content": "stable instructions"},
            {"role": "user", "content": "current input"},
        ],
    )

    assert provider._build_payload(request)["messages"] == request.messages
