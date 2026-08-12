import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import AuthContext
from app.core.security import verify_access_token
from app.database import async_session_factory
from app.services.metering import normalize_usage
from apps.api.app.gateway.llm import OpenAICompatibleProvider
from apps.api.app.gateway.llm import LLMGateway
from apps.api.app.main import app
from apps.api.app.routes import chat as chat_route
from apps.api.app.services.chat_events import ChatTraceEvent, format_sse_event
from apps.api.app.services.db.runtime_db import agent_skill_policy_db, skill_db
from apps.api.app.services.skill_creator import (
    build_skill_directory,
    detect_skill_creation_request,
    extract_skill_markdown,
)


def test_formats_sse_event_with_json_payload() -> None:
    event = ChatTraceEvent(
        event="node_started",
        data={"node": "llm_call", "label": "Call DeepSeek"},
    )

    payload = format_sse_event(event)

    assert payload.startswith("event: node_started\n")
    assert '"node":"llm_call"' in payload
    assert payload.endswith("\n\n")


def test_detects_chinese_skill_creation_request() -> None:
    result = detect_skill_creation_request("帮我创建一个用于总结会议纪要的 skill")

    assert result.is_skill_request is True
    assert "总结会议纪要" in result.topic


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _no_skill_router_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """平台内置 Skill 会让路由器在每次流式对话中触发一次 generate 调用；
    默认路由结果为“不使用 Skill”，需要选择 Skill 的测试再自行覆盖。"""
    from apps.api.app.gateway.llm import LLMCallResponse

    async def _generate(_self: LLMGateway, _request: object) -> LLMCallResponse:
        return LLMCallResponse(
            text=json.dumps({"use_skill": False, "skill_id": "", "reason": "general chat"}),
            provider="stub",
            model="stub",
        )

    monkeypatch.setattr(LLMGateway, "generate", _generate)


def _create_streaming_agent(client: TestClient) -> tuple[str, dict[str, str]]:
    suffix = uuid4().hex[:8]
    email = f"skill-intent-{suffix}@example.com"
    user_id = client.post(
        "/identity/users/register",
        json={"email": email, "display_name": "Owner", "password": "password123"},
    ).json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": user_id, "name": f"Skill Intent {suffix}"},
    ).json()["org_id"]
    login = client.post(
        "/identity/users/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']['access_token']}"}
    provider = client.post(
        "/model-providers",
        json={
            "actor_user_id": user_id,
            "org_id": org_id,
            "provider_key": "test-provider",
            "display_name": "Test Provider",
            "base_url": "https://example.test/v1",
            "api_key": "sk-test-key",
            "models": ["test-model"],
            "default_model": "test-model",
        },
        headers=headers,
    )
    assert provider.status_code == 200
    agent = client.post(
        "/agents",
        json={
            "actor_user_id": user_id,
            "org_id": org_id,
            "name": "Skill Intent Agent",
            "description": "",
            "model_provider": "test-provider",
            "model_name": "test-model",
        },
        headers=headers,
    )
    assert agent.status_code == 200
    return agent.json()["agent_id"], headers


def _parse_sse_events(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in body.split("\n\n"):
        event_name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = line.removeprefix("data: ")
        if event_name and data:
            payload = json.loads(data)
            payload["event"] = event_name
            events.append(payload)
    return events


@pytest.mark.parametrize(
    "message",
    [
        "帮我创建一个工作流，完成客户投诉分流",
        "生成一个销售周报模板",
        "新建一个 API 接口",
        "请解释如何创建一个 Skill",
        "是否能生成技能说明？",
        "创建一个 Skill 有什么用？",
        "创建一个 Skill 怎么样？",
    ],
)
def test_rejects_non_imperative_or_non_skill_creation(message: str) -> None:
    assert detect_skill_creation_request(message).is_skill_request is False


@pytest.mark.parametrize(
    "message, topic",
    [
        ("帮我创建一个用于总结会议纪要的 Skill", "总结会议纪要"),
        ("生成技能：客户投诉分流", "客户投诉分流"),
        ("create a skill for release-note summaries", "release-note summaries"),
    ],
)
def test_accepts_explicit_skill_creation(message: str, topic: str) -> None:
    result = detect_skill_creation_request(message)

    assert result.is_skill_request is True
    assert topic in result.topic


@pytest.mark.parametrize(
    "message",
    [
        "创建一个 Skill 有什么用？",
        "创建一个 Skill 怎么样？",
    ],
)
def test_skill_creation_consultation_uses_agent_without_creating_skill(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    agent_id, headers = _create_streaming_agent(client)

    def _unexpected_write(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("non-explicit workflow request must not create a skill")

    async def _unexpected_async_write(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("non-explicit workflow request must not create a skill")

    async def _stream_generate(*_args: object, **_kwargs: object):
        yield "ordinary agent response"

    monkeypatch.setattr(chat_route, "write_skill_file", _unexpected_write)
    monkeypatch.setattr(skill_db, "create_skill", _unexpected_async_write)
    monkeypatch.setattr(agent_skill_policy_db, "set_policy", _unexpected_async_write)
    monkeypatch.setattr(LLMGateway, "stream_generate", _stream_generate)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"agent_id": agent_id, "message": message},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = _parse_sse_events(body)
    assert not any(event["event"] == "skill_created" for event in events)
    assert any(
        event["event"] == "node_started" and event.get("node") == "agent_call" for event in events
    )


def test_autonomous_stream_emits_estimates_then_provider_final_usage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_id, headers = _create_streaming_agent(client)

    async def _stream_generate(self: LLMGateway, _request: object):
        yield "abcd"
        yield "efgh"
        self.last_normalized_usage = normalize_usage(
            {"prompt_tokens": 31, "completion_tokens": 9, "total_tokens": 40}
        )

    monkeypatch.setattr(LLMGateway, "stream_generate", _stream_generate)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"agent_id": agent_id, "message": "Explain the release plan"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _parse_sse_events("".join(response.iter_text()))

    usage_events = [event for event in events if event["event"].startswith("context_")]
    assert [event["event"] for event in usage_events] == [
        "context_preflight",
        "context_progress",
        "context_progress",
        "context_usage",
    ]
    assert usage_events[1]["output_tokens"] < usage_events[2]["output_tokens"]
    assert [event["usage_phase"] for event in usage_events] == [
        "preflight",
        "estimated",
        "estimated",
        "provider_final",
    ]
    assert usage_events[-1]["usage_scope"] == "chat"
    assert usage_events[-1]["usage_key"]
    assert len({event["usage_key"] for event in usage_events}) == 1
    assert usage_events[-1]["output_tokens"] == 9
    assert [event["text"] for event in events if event["event"] == "token"] == ["abcd", "efgh"]


def test_explicit_skill_stream_reports_usage_without_emitting_tokens(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    agent_id, headers = _create_streaming_agent(client)
    lifecycle: list[str] = []

    async def _stream_generate(self: LLMGateway, _request: object):
        yield "---\nname: release-notes\ndescription: Draft release notes.\n---\n# Release Notes\n"
        yield "\n## Steps\n1. Summarize the changes.\n"
        self.last_normalized_usage = normalize_usage(
            {"prompt_tokens": 41, "completion_tokens": 12, "total_tokens": 53}
        )

    def _write_skill_file(*_args: object, **_kwargs: object) -> Path:
        lifecycle.append("write")
        return tmp_path / "release-notes" / "SKILL.md"

    async def _create_skill(*_args: object, **_kwargs: object) -> SimpleNamespace:
        lifecycle.append("create")
        return SimpleNamespace(skill_id="skl-test", name="release-notes")

    async def _set_policy(*_args: object, **_kwargs: object) -> None:
        lifecycle.append("policy")

    monkeypatch.setattr(LLMGateway, "stream_generate", _stream_generate)
    monkeypatch.setattr(chat_route, "write_skill_file", _write_skill_file)
    monkeypatch.setattr(skill_db, "create_skill", _create_skill)
    monkeypatch.setattr(agent_skill_policy_db, "set_policy", _set_policy)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"agent_id": agent_id, "message": "create a skill for release-note summaries"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _parse_sse_events("".join(response.iter_text()))

    usage_events = [event for event in events if event["event"].startswith("context_")]
    assert [event["event"] for event in usage_events] == [
        "context_preflight",
        "context_progress",
        "context_progress",
        "context_usage",
    ]
    assert usage_events[1]["output_tokens"] < usage_events[2]["output_tokens"]
    assert [event["usage_phase"] for event in usage_events] == [
        "preflight",
        "estimated",
        "estimated",
        "provider_final",
    ]
    assert usage_events[-1]["usage_scope"] == "skill_create"
    assert len({event["usage_key"] for event in usage_events}) == 1
    assert not [event for event in events if event["event"] == "token"]
    assert lifecycle == ["write", "create", "policy"]
    context_usage_index = next(
        index for index, event in enumerate(events) if event["event"] == "context_usage"
    )
    skill_created_index = next(
        index for index, event in enumerate(events) if event["event"] == "skill_created"
    )
    assert context_usage_index < skill_created_index


def test_autonomous_stream_marks_missing_provider_usage_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_id, headers = _create_streaming_agent(client)

    async def _stream_generate(_self: LLMGateway, _request: object):
        yield "abcd"
        yield "efgh"

    monkeypatch.setattr(LLMGateway, "stream_generate", _stream_generate)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"agent_id": agent_id, "message": "Explain the release plan"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _parse_sse_events("".join(response.iter_text()))

    usage_events = [event for event in events if event["event"].startswith("context_")]
    assert [event["event"] for event in usage_events] == [
        "context_preflight",
        "context_progress",
        "context_progress",
        "context_usage",
    ]
    assert usage_events[-1]["usage_phase"] == "unavailable"
    assert not any(event.get("usage_phase") == "provider_final" for event in usage_events)


async def test_autonomous_stream_cancellation_propagates_without_error_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_id, headers = _create_streaming_agent(client)

    async def _stream_generate(_self: LLMGateway, _request: object):
        yield "partial"
        raise asyncio.CancelledError("fake stream cancellation")

    monkeypatch.setattr(LLMGateway, "stream_generate", _stream_generate)

    token = headers["Authorization"].removeprefix("Bearer ")
    payload = verify_access_token(token)
    assert payload is not None
    events: list[str] = []
    rollback_calls: list[str] = []

    async with async_session_factory() as db:
        original_rollback = db.rollback

        async def _track_rollback() -> None:
            rollback_calls.append("rollback")
            await original_rollback()

        monkeypatch.setattr(db, "rollback", _track_rollback)
        stream = chat_route._chat_stream_events(
            request=chat_route.ChatRequest(agent_id=agent_id, message="Explain the release plan"),
            auth=AuthContext.from_jwt(payload),
            db=db,
        )
        with pytest.raises(asyncio.CancelledError, match="fake stream cancellation"):
            async for event in stream:
                events.append(event)

    assert any(event.startswith("event: token\n") for event in events)
    assert not any(event.startswith("event: error\n") for event in events)
    assert rollback_calls == ["rollback"]


def test_autonomous_stream_provider_error_emits_error_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_id, headers = _create_streaming_agent(client)

    async def _stream_generate(_self: LLMGateway, _request: object):
        yield "partial"
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(LLMGateway, "stream_generate", _stream_generate)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"agent_id": agent_id, "message": "Explain the release plan"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _parse_sse_events("".join(response.iter_text()))

    assert events[-1]["event"] == "error"
    assert events[-1]["error"] == "provider unavailable"
    assert not any(event["event"] == "run_finished" for event in events)


def test_invalid_skill_markdown_ends_with_error_without_provider_final_or_skill_created(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_id, headers = _create_streaming_agent(client)

    async def _stream_generate(self: LLMGateway, _request: object):
        yield "This is not a SKILL.md document."
        self.last_normalized_usage = normalize_usage(
            {"prompt_tokens": 21, "completion_tokens": 7, "total_tokens": 28}
        )

    def _unexpected_write(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid Markdown must not write a skill file")

    monkeypatch.setattr(LLMGateway, "stream_generate", _stream_generate)
    monkeypatch.setattr(chat_route, "write_skill_file", _unexpected_write)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"agent_id": agent_id, "message": "create a skill for release-note summaries"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _parse_sse_events("".join(response.iter_text()))

    assert events[-1]["event"] == "error"
    assert not any(event.get("usage_phase") == "provider_final" for event in events)
    assert not any(event["event"] == "skill_created" for event in events)


@pytest.mark.parametrize(
    ("failing_stage", "expected_persistence_calls"),
    [
        ("write", ["write"]),
        ("create", ["write", "create"]),
        ("policy", ["write", "create", "policy"]),
    ],
)
def test_skill_persistence_failures_emit_unavailable_usage_before_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failing_stage: str,
    expected_persistence_calls: list[str],
) -> None:
    agent_id, headers = _create_streaming_agent(client)
    persistence_calls: list[str] = []

    async def _stream_generate(self: LLMGateway, _request: object):
        yield (
            "---\nname: release-notes\ndescription: Draft release notes.\n---\n# Release Notes\n"
        )
        yield "\n## Steps\n1. Summarize the changes.\n"
        self.last_normalized_usage = normalize_usage(
            {"prompt_tokens": 41, "completion_tokens": 12, "total_tokens": 53}
        )

    def _write_skill_file(*_args: object, **_kwargs: object) -> Path:
        persistence_calls.append("write")
        if failing_stage == "write":
            raise RuntimeError("write failed")
        return tmp_path / "release-notes" / "SKILL.md"

    async def _create_skill(*_args: object, **_kwargs: object) -> SimpleNamespace:
        persistence_calls.append("create")
        if failing_stage == "create":
            raise RuntimeError("create failed")
        return SimpleNamespace(skill_id="skl-test", name="release-notes")

    async def _set_policy(*_args: object, **_kwargs: object) -> None:
        persistence_calls.append("policy")
        if failing_stage == "policy":
            raise RuntimeError("policy failed")

    monkeypatch.setattr(LLMGateway, "stream_generate", _stream_generate)
    monkeypatch.setattr(chat_route, "write_skill_file", _write_skill_file)
    monkeypatch.setattr(skill_db, "create_skill", _create_skill)
    monkeypatch.setattr(agent_skill_policy_db, "set_policy", _set_policy)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"agent_id": agent_id, "message": "create a skill for release-note summaries"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _parse_sse_events("".join(response.iter_text()))

    context_events = [event for event in events if event["event"].startswith("context_")]
    assert [event["event"] for event in context_events] == [
        "context_preflight",
        "context_progress",
        "context_progress",
        "context_usage",
    ]
    assert context_events[-1]["usage_phase"] == "unavailable"
    assert persistence_calls == expected_persistence_calls
    assert events[-1]["event"] == "error"
    assert events[-1]["error"] == f"{failing_stage} failed"
    assert not any(event.get("usage_phase") == "provider_final" for event in events)
    assert not any(event["event"] == "skill_created" for event in events)
    assert not any(event["event"] == "run_finished" for event in events)


def test_extract_skill_markdown_from_fenced_llm_output() -> None:
    markdown = extract_skill_markdown(
        """Here is the skill:

```markdown
---
name: meeting-summary
description: Summarize meeting notes into decisions and actions.
---

# Meeting Summary

## Steps
1. Read the notes.
```
"""
    )

    assert markdown.startswith("---\nname: meeting-summary")
    assert "# Meeting Summary" in markdown


def test_build_skill_directory_sanitizes_skill_name(tmp_path: Path) -> None:
    directory = build_skill_directory(tmp_path, "会议 总结/Skill")

    assert directory == tmp_path / "hui-yi-zong-jie-skill"


def test_extracts_openai_compatible_stream_delta() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://example.test",
        api_key="test-key",
        provider_key="deepseek",
    )

    assert provider._extract_stream_delta({"choices": [{"delta": {"content": "hello"}}]}) == "hello"
    assert provider._extract_stream_delta({"choices": [{"delta": {}}]}) == ""
