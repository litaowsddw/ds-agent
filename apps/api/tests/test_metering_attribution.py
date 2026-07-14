"""Trusted attribution contracts for Gateway, Chat, and Workflow calls."""

import asyncio
import inspect
import os
import sys
from dataclasses import dataclass
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


# Route imports require an engine during module import. SQLite is sufficient:
# unauthenticated requests must be rejected before any database operation.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./task3-attribution.db")

from app.schemas.gateway import LLMGenerateRequest  # noqa: E402


class _AllowingLimiter:
    async def require(self, **_kwargs: object) -> None:
        return None


class _RateLimitExceeded(RuntimeError):
    pass


def _gateway_components():
    """Load the real Gateway without polluting other test modules at collection."""

    if "apps.api.app.gateway.rate_limiter" not in sys.modules:
        rate_limiter_module = ModuleType("apps.api.app.gateway.rate_limiter")
        rate_limiter_module.HybridRateLimiter = _AllowingLimiter
        rate_limiter_module.RateLimitExceeded = _RateLimitExceeded
        rate_limiter_module.rate_limiter = _AllowingLimiter()
        sys.modules["apps.api.app.gateway.rate_limiter"] = rate_limiter_module

    from app.routes.gateway import generate_llm, router as gateway_router
    from apps.api.app.gateway.llm import LLMCallResponse, LLMGateway
    from packages.runtime.llm_caller import LLMCallerAdapter

    return generate_llm, gateway_router, LLMCallResponse, LLMGateway, LLMCallerAdapter


class _UsageProvider:
    def generate(self, request: object) -> object:
        _, _, LLMCallResponse, _, _ = _gateway_components()
        return LLMCallResponse(
            text="ok",
            provider=str(getattr(request, "provider")),
            model=str(getattr(request, "model")),
            usage={"prompt_tokens": 3, "completion_tokens": 2},
        )


@dataclass
class _RecordingUsageRecorder:
    started: list[object]
    terminal: list[object]

    def __init__(self) -> None:
        self.started = []
        self.terminal = []

    async def record_started(self, context: object) -> None:
        self.started.append(context)

    async def record_terminal(self, call_id: str, outcome: object) -> None:
        assert call_id
        self.terminal.append(outcome)


def test_gateway_request_forbids_client_identity_fields() -> None:
    with pytest.raises(ValidationError):
        LLMGenerateRequest(
            provider="mock",
            model="m",
            prompt="hello",
            org_id="spoofed-org",
            actor_user_id="spoofed-actor",
        )


def test_gateway_generate_requires_authenticated_user() -> None:
    generate_llm, gateway_router, _, _, _ = _gateway_components()
    app = FastAPI()
    app.include_router(gateway_router, prefix="/gateway")
    with TestClient(app) as client:
        response = client.post(
            "/gateway/llm/generate",
            json={"provider": "mock", "model": "m", "prompt": "hello"},
        )
        fallback_response = client.post(
            "/gateway/llm/generate?actor_user_id=spoofed",
            json={"provider": "mock", "model": "m", "prompt": "hello"},
        )
    assert response.status_code == fallback_response.status_code == 401
    assert "auth" in str(inspect.signature(generate_llm))


def test_workflow_llm_usage_contains_server_owned_run_and_node_context() -> None:
    asyncio.run(_workflow_llm_usage_contains_server_owned_run_and_node_context())


async def _workflow_llm_usage_contains_server_owned_run_and_node_context() -> None:
    _, _, _, LLMGateway, _ = _gateway_components()
    recorder = _RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={"mock": _UsageProvider()},
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )

    await gateway.generate_from_workflow_node(
        {
            "id": "llm_1",
            "provider": "mock",
            "model": "m",
            "_org_id": "org_1",
            "_actor_user_id": "user_1",
            "_agent_id": "agent_1",
            "_workflow_id": "workflow_1",
            "_workflow_version_id": "version_1",
            "_workflow_run_id": "run_1",
            "_workflow_node_id": "llm_1",
        },
        {"workflow_input": {"text": "hello"}},
    )

    event = recorder.started[0]
    assert event.org_id == "org_1"
    assert event.actor_user_id == "user_1"
    assert event.agent_id == "agent_1"
    assert event.workflow_id == "workflow_1"
    assert event.workflow_version_id == "version_1"
    assert event.workflow_run_id == "run_1"
    assert event.workflow_node_id == "llm_1"
    assert len(recorder.started) == len(recorder.terminal) == 1


def test_chat_adapter_usage_contains_agent_and_session_context_once() -> None:
    asyncio.run(_chat_adapter_usage_contains_agent_and_session_context_once())


async def _chat_adapter_usage_contains_agent_and_session_context_once() -> None:
    _, _, _, LLMGateway, LLMCallerAdapter = _gateway_components()
    recorder = _RecordingUsageRecorder()
    gateway = LLMGateway(
        providers={"mock": _UsageProvider()},
        limiter=_AllowingLimiter(),
        usage_recorder=recorder,
    )
    adapter = LLMCallerAdapter(
        gateway=gateway,
        provider="mock",
        model="m",
        org_id="org_1",
        actor_user_id="user_1",
        metadata={"agent_id": "agent_1", "session_id": "session_1"},
    )

    assert await adapter.call("hello") == "ok"
    event = recorder.started[0]
    assert event.org_id == "org_1"
    assert event.actor_user_id == "user_1"
    assert event.agent_id == "agent_1"
    assert event.session_id == "session_1"
    assert len(recorder.started) == len(recorder.terminal) == 1
