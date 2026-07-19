"""Chat workflow execution mode tests."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.app.gateway.llm import LLMCallRequest, LLMCallResponse, LLMStreamChunk
from apps.api.app.main import app
from apps.api.app.routes import workflow_runs as workflow_runs_route


class _ChunkedWorkflowProvider:
    """Workflow-provider double that emits two chunks and terminal usage."""

    def __init__(self, **_kwargs: object) -> None:
        pass

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        return LLMCallResponse(
            text="fallback response",
            provider=request.provider,
            model=request.model,
            usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            raw={},
        )

    def stream_generate(self, _request: LLMCallRequest):
        yield LLMStreamChunk(text="first ")
        yield LLMStreamChunk(text="second")
        yield LLMStreamChunk(
            usage={"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}
        )


class _UnavailableUsageWorkflowProvider(_ChunkedWorkflowProvider):
    """Workflow-provider double that completes without terminal usage data."""

    def stream_generate(self, _request: LLMCallRequest):
        yield LLMStreamChunk(text="first ")
        yield LLMStreamChunk(text="second")


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _suffix(label: str) -> str:
    return f"{label}-{uuid4().hex[:8]}"


def _create_owner_org_agent(client: TestClient, suffix: str) -> tuple[str, str, str, dict[str, str]]:
    owner_email = f"owner-{suffix}@example.com"
    owner_user_id = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "Owner", "password": "password123"},
    ).json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": f"Org {suffix}"},
    ).json()["org_id"]
    login = client.post(
        "/identity/users/login",
        json={"email": owner_email, "password": "password123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']['access_token']}"}
    agent_id = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": f"Agent {suffix}", "description": ""},
        headers=headers,
    ).json()["agent_id"]
    return owner_user_id, org_id, agent_id, headers


def _create_agent(
    client: TestClient,
    owner_user_id: str,
    org_id: str,
    name: str,
    headers: dict[str, str],
) -> str:
    return client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": name, "description": ""},
        headers=headers,
    ).json()["agent_id"]


def _create_published_passthrough_workflow(client: TestClient, owner_user_id: str, agent_id: str) -> str:
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "name": "Passthrough",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [{"id": "start", "type": "start", "config": {}}, {"id": "end", "type": "end", "config": {}}],
                "edges": [{"source": "start", "target": "end"}],
            },
        },
    ).json()
    publish = client.post(f"/workflows/{workflow['workflow_id']}/publish", json={"actor_user_id": owner_user_id})
    assert publish.status_code == 200
    return workflow["workflow_id"]


def _create_published_llm_workflow(
    client: TestClient,
    owner_user_id: str,
    agent_id: str,
) -> str:
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "name": "LLM Workflow",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {
                        "id": "llm",
                        "type": "llm",
                        "config": {
                            "provider": "workflow-test-provider",
                            "model": "workflow-test-model",
                            "prompt": "summarize workflow input",
                        },
                    },
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "llm"},
                    {"source": "llm", "target": "end"},
                ],
            },
        },
    ).json()
    publish = client.post(f"/workflows/{workflow['workflow_id']}/publish", json={"actor_user_id": owner_user_id})
    assert publish.status_code == 200
    return workflow["workflow_id"]


def _create_model_provider(
    client: TestClient,
    owner_user_id: str,
    org_id: str,
    headers: dict[str, str],
) -> None:
    response = client.post(
        "/model-providers",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "provider_key": "workflow-test-provider",
            "display_name": "Workflow Test Provider",
            "base_url": "https://example.test/v1",
            "api_key": "test-key",
            "models": ["workflow-test-model"],
            "default_model": "workflow-test-model",
        },
        headers=headers,
    )
    assert response.status_code == 200


def _parse_sse_events(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in body.split("\n\n"):
        event_name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            if line.startswith("data: "):
                data = line.removeprefix("data: ")
        if event_name and data:
            import json

            payload = json.loads(data)
            payload["event"] = event_name
            events.append(payload)
    return events


def test_chat_workflow_mode_executes_published_workflow_and_saves_session(client: TestClient) -> None:
    suffix = _suffix("chat-wf")
    owner_user_id, _org_id, agent_id, headers = _create_owner_org_agent(client, suffix)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    response = client.post(
        "/chat/",
        json={
            "agent_id": agent_id,
            "message": "稳定输入",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "workflow"
    assert body["workflow_id"] == workflow_id
    assert body["workflow_run_id"]
    assert "稳定输入" in body["response"]

    messages = client.get(f"/chat/sessions/{body['session_id']}/messages").json()["messages"]
    assert [message["role"] for message in messages][-2:] == ["user", "assistant"]
    assistant_message = messages[-1]
    assert assistant_message["meta_info"]["execution_mode"] == "workflow"
    assert assistant_message["meta_info"]["workflow_id"] == body["workflow_id"]
    assert assistant_message["meta_info"]["workflow_run_id"] == body["workflow_run_id"]


def test_canonical_session_messages_include_workflow_metadata(client: TestClient) -> None:
    suffix = _suffix("session-wf-meta")
    owner_user_id, _org_id, agent_id, headers = _create_owner_org_agent(client, suffix)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    chat_response = client.post(
        "/chat/",
        json={
            "agent_id": agent_id,
            "message": "canonical metadata",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
        headers=headers,
    )

    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    messages_response = client.get(
        f"/sessions/{chat_body['session_id']}/messages",
        params={"actor_user_id": owner_user_id},
    )

    assert messages_response.status_code == 200
    assistant_message = messages_response.json()[-1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["meta_info"]["execution_mode"] == "workflow"
    assert assistant_message["meta_info"]["workflow_id"] == workflow_id
    assert assistant_message["meta_info"]["workflow_run_id"] == chat_body["workflow_run_id"]


def test_streaming_workflow_mode_saves_metadata_in_history(client: TestClient) -> None:
    suffix = _suffix("stream-wf-meta")
    owner_user_id, _org_id, agent_id, headers = _create_owner_org_agent(client, suffix)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "agent_id": agent_id,
            "message": "stream metadata",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
        headers=headers,
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    events = _parse_sse_events(body)
    run_finished = next(event for event in events if event["event"] == "run_finished")
    session_id = str(run_finished["session_id"])
    workflow_run_id = str(run_finished["workflow_run_id"])

    messages_response = client.get(
        f"/sessions/{session_id}/messages",
        params={"actor_user_id": owner_user_id},
    )
    assert messages_response.status_code == 200
    assistant_message = messages_response.json()[-1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["meta_info"]["execution_mode"] == "workflow"
    assert assistant_message["meta_info"]["workflow_id"] == workflow_id
    assert assistant_message["meta_info"]["workflow_run_id"] == workflow_run_id


def test_streaming_workflow_emits_llm_usage_before_run_finished(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = _suffix("stream-wf-usage")
    owner_user_id, org_id, agent_id, headers = _create_owner_org_agent(client, suffix)
    _create_model_provider(client, owner_user_id, org_id, headers)
    workflow_id = _create_published_llm_workflow(client, owner_user_id, agent_id)
    monkeypatch.setattr(workflow_runs_route, "OpenAICompatibleProvider", _ChunkedWorkflowProvider)

    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "agent_id": agent_id,
            "message": "stream workflow usage",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _parse_sse_events("".join(response.iter_text()))

    workflow_progress = [event for event in events if event["event"] == "context_progress"]
    run_finished = next(event for event in events if event["event"] == "run_finished")
    assert len(workflow_progress) >= 2
    assert all(item["usage_scope"] == "workflow" for item in workflow_progress)
    assert all(item["workflow_node_id"] == "llm" for item in workflow_progress)
    assert events.index(workflow_progress[-1]) < events.index(run_finished)

    persisted_run = client.get(
        f"/workflow-runs/{run_finished['workflow_run_id']}",
        params={"actor_user_id": owner_user_id},
    ).json()
    assert persisted_run["status"] == "succeeded"


def test_streaming_workflow_reports_unavailable_usage_when_provider_omits_usage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = _suffix("stream-wf-usage-unavailable")
    owner_user_id, org_id, agent_id, headers = _create_owner_org_agent(client, suffix)
    _create_model_provider(client, owner_user_id, org_id, headers)
    workflow_id = _create_published_llm_workflow(client, owner_user_id, agent_id)
    monkeypatch.setattr(
        workflow_runs_route, "OpenAICompatibleProvider", _UnavailableUsageWorkflowProvider
    )

    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "agent_id": agent_id,
            "message": "stream unavailable usage",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
        headers=headers,
    ) as response:
        assert response.status_code == 200
        events = _parse_sse_events("".join(response.iter_text()))

    context_usage = [event for event in events if event["event"] == "context_usage"]
    assert context_usage[-1]["usage_phase"] == "unavailable"


def test_normal_and_stream_workflow_mode_emit_matching_metadata(client: TestClient) -> None:
    suffix = _suffix("chat-parity")
    owner_user_id, _org_id, agent_id, headers = _create_owner_org_agent(client, suffix)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    normal_response = client.post(
        "/chat/",
        json={
            "agent_id": agent_id,
            "message": "normal mode",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
        headers=headers,
    )
    assert normal_response.status_code == 200
    normal_body = normal_response.json()

    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "agent_id": agent_id,
            "message": "stream mode",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
        headers=headers,
    ) as response:
        assert response.status_code == 200
        stream_body = "".join(response.iter_text())
    events = _parse_sse_events(stream_body)
    stream_finished = next(event for event in events if event["event"] == "run_finished")

    assert normal_body["mode"] == stream_finished["mode"] == "workflow"
    assert normal_body["workflow_id"] == stream_finished["workflow_id"] == workflow_id
    assert normal_body["workflow_run_id"]
    assert stream_finished["workflow_run_id"]


def test_chat_history_preserves_empty_metadata_for_autonomous_messages(client: TestClient) -> None:
    suffix = _suffix("chat-auto-meta")
    owner_user_id, _org_id, agent_id, _headers = _create_owner_org_agent(client, suffix)
    session_id = client.post(
        "/sessions",
        json={"actor_user_id": owner_user_id, "agent_id": agent_id},
    ).json()["session_id"]

    append_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"actor_user_id": owner_user_id, "role": "assistant", "content": "自主回复"},
    )

    assert append_response.status_code == 200
    messages_response = client.get(f"/chat/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    message = messages_response.json()["messages"][0]
    assert message["role"] == "assistant"
    assert message["meta_info"] == {}


def test_chat_workflow_mode_rejects_cross_agent_workflow(client: TestClient) -> None:
    owner_user_id, org_id, agent_a, headers = _create_owner_org_agent(client, _suffix("chat-cross-a"))
    agent_b = _create_agent(client, owner_user_id, org_id, "Agent B", headers)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_b)

    response = client.post(
        "/chat/",
        json={
            "agent_id": agent_a,
            "message": "try cross",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "Workflow 必须属于当前 Agent" in response.text
