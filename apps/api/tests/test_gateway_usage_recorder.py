"""Contract tests for normalized Gateway usage recording."""

import asyncio

import pytest


class _AllowingLimiter:
    async def require(self, **_kwargs: object) -> None:
        return None


from apps.api.app.gateway.rate_limiter import RateLimitExceeded  # noqa: E402
from apps.api.app.services.db.metering_db import UsageEventInput  # noqa: E402
from apps.api.app.gateway.llm import (  # noqa: E402
    GatewayProviderError,
    LLMCallRequest,
    LLMCallResponse,
    LLMGateway,
    LLMStreamChunk,
    OpenAICompatibleProvider,
)


class RecordingUsageRecorder:
    def __init__(self) -> None:
        self.started: list[object] = []
        self.events: list[object] = []

    async def record_started(self, context: object) -> None:
        self.started.append(context)

    async def record_terminal(self, call_id: str, outcome: object) -> None:
        assert call_id
        self.events.append(outcome)


class UsageProvider:
    def __init__(self, usage: dict[str, object]) -> None:
        self.usage = usage

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        return LLMCallResponse(
            text="ok",
            provider=request.provider,
            model=request.model,
            usage=self.usage,
        )


class FailingProvider:
    def generate(self, _request: LLMCallRequest) -> LLMCallResponse:
        raise RuntimeError("provider unavailable")


class StreamProvider:
    def stream_generate(self, _request: LLMCallRequest):
        yield "a"
        yield "b"


class FailingStreamProvider:
    def stream_generate(self, _request: LLMCallRequest):
        yield "a"
        raise RuntimeError("stream provider unavailable")


class FinalUsageStreamProvider:
    def stream_generate(self, _request: LLMCallRequest):
        yield LLMStreamChunk(text="a")
        yield LLMStreamChunk(
            usage={
                "prompt_tokens": 20,
                "completion_tokens": 4,
                "prompt_tokens_details": {"cached_tokens": 10},
            }
        )


class RejectingLimiter:
    async def require(self, **_kwargs: object) -> None:
        raise RateLimitExceeded("limited")


def _request() -> LLMCallRequest:
    return LLMCallRequest(
        provider="mock",
        model="model-1",
        prompt="must never be persisted",
        metadata={"org_id": "org-1", "source": "chat", "api_name": "chat.completions"},
    )


def test_gateway_usage_recorder_imports_real_metering_module() -> None:
    assert UsageEventInput.__module__ == "apps.api.app.services.db.metering_db"


def test_gateway_records_provider_cache_read_without_inventing_cache_miss() -> None:
    recorder = RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={
            "mock": UsageProvider(
                {"prompt_tokens": 20, "completion_tokens": 4, "prompt_cache_hit_tokens": 10}
            )
        },
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )

    asyncio.run(gateway.generate(_request()))

    assert len(recorder.started) == 1
    assert len(recorder.events) == 1
    event = recorder.events[0]
    assert event.input_tokens == 20
    assert event.output_tokens == 4
    assert event.total_tokens == 24
    assert event.cache_read_input_tokens == 10
    assert event.cache_miss_input_tokens == 10
    assert event.usage_status == "provider_final"
    assert event.cache_usage_status == "known"
    assert event.prompt is None if hasattr(event, "prompt") else True


def test_gateway_keeps_missing_provider_cache_usage_unknown() -> None:
    recorder = RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={"mock": UsageProvider({"prompt_tokens": 20, "completion_tokens": 4})},
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )

    asyncio.run(gateway.generate(_request()))

    event = recorder.events[0]
    assert event.cache_read_input_tokens is None
    assert event.cache_miss_input_tokens is None
    assert event.cache_usage_status == "unknown"


def test_gateway_marks_stream_without_final_usage_as_unavailable() -> None:
    recorder = RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={"mock": StreamProvider()},
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )

    async def consume() -> list[str]:
        return [chunk async for chunk in gateway.stream_generate(_request())]

    assert asyncio.run(consume()) == ["a", "b"]
    assert len(recorder.events) == 1
    event = recorder.events[0]
    assert event.usage_status == "unavailable"
    assert event.input_tokens is None
    assert event.output_tokens is None


def test_gateway_records_cancelled_terminal_event_when_stream_is_closed_early() -> None:
    recorder = RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={"mock": StreamProvider()},
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )

    async def consume_one_then_close() -> str:
        stream = gateway.stream_generate(_request())
        first_chunk = await anext(stream)
        await stream.aclose()
        return first_chunk

    assert asyncio.run(consume_one_then_close()) == "a"
    assert len(recorder.started) == 1
    assert len(recorder.events) == 1
    event = recorder.events[0]
    assert event.dispatch_status == "cancelled"
    assert event.usage_status == "unavailable"
    assert event.input_tokens is None
    assert event.output_tokens is None


def test_explicit_chat_stream_boundary_closes_normal_gateway_stream_once() -> None:
    recorder = RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={"mock": StreamProvider()},
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )

    async def consume_through_chat_boundary() -> list[str]:
        llm_stream = gateway.stream_generate(_request())
        chunks: list[str] = []
        try:
            async for chunk in llm_stream:
                chunks.append(chunk)
        finally:
            await llm_stream.aclose()
        return chunks

    assert asyncio.run(consume_through_chat_boundary()) == ["a", "b"]
    assert len(recorder.events) == 1
    assert recorder.events[0].dispatch_status == "succeeded"


def test_gateway_records_one_failed_terminal_event_for_stream_exception() -> None:
    recorder = RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={"mock": FailingStreamProvider()},
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )

    async def consume() -> list[str]:
        return [chunk async for chunk in gateway.stream_generate(_request())]

    with pytest.raises(GatewayProviderError):
        asyncio.run(consume())

    assert len(recorder.events) == 1
    assert recorder.events[0].dispatch_status == "failed"
    assert recorder.events[0].usage_status == "unavailable"


def test_gateway_records_only_final_stream_usage_with_nested_cache_tokens() -> None:
    recorder = RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={"mock": FinalUsageStreamProvider()},
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )

    async def consume() -> list[str]:
        return [chunk async for chunk in gateway.stream_generate(_request())]

    assert asyncio.run(consume()) == ["a"]
    event = recorder.events[0]
    assert event.input_tokens == 20
    assert event.output_tokens == 4
    assert event.cache_read_input_tokens == 10
    assert event.cache_miss_input_tokens == 10


@pytest.mark.parametrize(
    ("providers", "limiter", "expected_status"),
    [
        ({}, _AllowingLimiter(), "failed"),
        ({"mock": UsageProvider({})}, RejectingLimiter(), "rate_limited"),
        ({"mock": FailingProvider()}, _AllowingLimiter(), "failed"),
    ],
)
def test_gateway_records_one_terminal_event_for_all_error_paths(
    providers: dict[str, object], limiter: object, expected_status: str
) -> None:
    recorder = RecordingUsageRecorder()
    gateway = LLMGateway(
        providers=providers,
        limiter=limiter,
        usage_recorder=recorder,
    )

    with pytest.raises((GatewayProviderError, RateLimitExceeded)):
        asyncio.run(gateway.generate(_request()))

    assert len(recorder.started) == 1
    assert len(recorder.events) == 1
    assert recorder.events[0].dispatch_status == expected_status
    assert recorder.events[0].usage_status == "unavailable"


def test_openai_stream_payload_requests_final_usage() -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://example.test",
        api_key="secret",
        provider_key="openai",
    )

    payload = provider._build_payload(_request(), stream=True)

    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
