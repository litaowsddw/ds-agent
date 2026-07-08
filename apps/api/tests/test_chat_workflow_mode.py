"""Chat workflow execution mode tests."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _suffix(label: str) -> str:
    return f"{label}-{uuid4().hex[:8]}"


def _create_owner_org_agent(client: TestClient, suffix: str) -> tuple[str, str, str]:
    owner_user_id = client.post(
        "/identity/users/register",
        json={"email": f"owner-{suffix}@example.com", "display_name": "Owner", "password": "password123"},
    ).json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": f"Org {suffix}"},
    ).json()["org_id"]
    agent_id = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": f"Agent {suffix}", "description": ""},
    ).json()["agent_id"]
    return owner_user_id, org_id, agent_id


def _create_agent(client: TestClient, owner_user_id: str, org_id: str, name: str) -> str:
    return client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": name, "description": ""},
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
    owner_user_id, org_id, agent_id = _create_owner_org_agent(client, suffix)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    response = client.post(
        "/chat/",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "org_id": org_id,
            "message": "稳定输入",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
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
    owner_user_id, org_id, agent_id = _create_owner_org_agent(client, suffix)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    chat_response = client.post(
        "/chat/",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "org_id": org_id,
            "message": "canonical metadata",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
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
    owner_user_id, org_id, agent_id = _create_owner_org_agent(client, suffix)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "org_id": org_id,
            "message": "stream metadata",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
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


def test_chat_history_preserves_empty_metadata_for_autonomous_messages(client: TestClient) -> None:
    suffix = _suffix("chat-auto-meta")
    owner_user_id, _org_id, agent_id = _create_owner_org_agent(client, suffix)
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
    owner_user_id, org_id, agent_a = _create_owner_org_agent(client, _suffix("chat-cross-a"))
    agent_b = _create_agent(client, owner_user_id, org_id, "Agent B")
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_b)

    response = client.post(
        "/chat/",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_a,
            "org_id": org_id,
            "message": "try cross",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
    )

    assert response.status_code == 400
    assert "Workflow 必须属于当前 Agent" in response.text
