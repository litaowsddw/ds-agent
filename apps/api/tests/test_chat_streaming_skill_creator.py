import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

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


def test_non_explicit_workflow_request_uses_agent_without_creating_skill(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
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
        json={"agent_id": agent_id, "message": "创建一个工作流"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = _parse_sse_events(body)
    assert not any(event["event"] == "skill_created" for event in events)
    assert any(
        event["event"] == "node_started" and event.get("node") == "agent_call" for event in events
    )


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
