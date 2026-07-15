"""WorkflowExecutionService contract tests."""

from datetime import datetime, timezone
from types import SimpleNamespace

from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.routes.workflow_runs import _to_run_response


def test_run_response_includes_iso_timestamps() -> None:
    created_at = datetime(2026, 7, 12, 1, 2, 3, tzinfo=timezone.utc)
    run = SimpleNamespace(
        run_id="run-timestamps",
        org_id="org-a",
        workflow_id="workflow-a",
        version_id="version-a",
        agent_id="agent-a",
        input_data="{}",
        status="succeeded",
        output_data="{}",
        error_message="",
        created_by="user-a",
        created_at=created_at,
    )

    body = _to_run_response(run).model_dump(mode="json")  # type: ignore[arg-type]

    assert body["created_at"] == "2026-07-12T01:02:03Z"
    assert body["updated_at"] is None


def _suffix(label: str) -> str:
    return f"{label}-{uuid4().hex[:8]}"


def _create_owner_org_agent(client: TestClient, suffix: str) -> tuple[str, str, str, dict[str, str]]:
    email = f"owner-{suffix}@example.com"
    owner_user_id = client.post(
        "/identity/users/register",
        json={
            "email": email,
            "display_name": "Owner",
            "password": "password123",
        },
    ).json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": f"Org {suffix}"},
    ).json()["org_id"]
    agent_id = client.post(
        "/agents",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "name": f"Agent {suffix}",
            "description": "",
        },
    ).json()["agent_id"]
    login = client.post(
        "/identity/users/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']['access_token']}"}
    return owner_user_id, org_id, agent_id, headers


def _create_and_publish_workflow(
    client: TestClient,
    *,
    actor_user_id: str,
    agent_id: str,
    definition: dict[str, object],
) -> str:
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": actor_user_id,
            "agent_id": agent_id,
            "name": "Contract Workflow",
            "description": "",
            "draft_definition": definition,
        },
    ).json()
    publish = client.post(
        f"/workflows/{workflow['workflow_id']}/publish",
        json={"actor_user_id": actor_user_id},
    )
    assert publish.status_code == 200
    return publish.json()["version_id"]


def test_workflow_execution_service_persists_node_runs_for_success() -> None:
    with TestClient(app) as client:
        actor_user_id, _org_id, agent_id, owner_headers = _create_owner_org_agent(
            client, _suffix("wf-service-ok")
        )
        version_id = _create_and_publish_workflow(
            client,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            definition={
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [{"source": "start", "target": "end"}],
            },
        )

        run_response = client.post(
            "/workflow-runs",
            json={
                "version_id": version_id,
                "input_data": {"text": "hello"},
                "async_mode": False,
            },
            headers=owner_headers,
        )

        assert run_response.status_code == 200
        run = run_response.json()
        assert run["created_at"]
        assert run["updated_at"] is None
        assert run["status"] == "succeeded"
        node_runs_response = client.get(
            f"/workflow-runs/{run['run_id']}/nodes",
            params={"actor_user_id": actor_user_id},
        )
        assert node_runs_response.status_code == 200
        node_runs = node_runs_response.json()
        assert [node["node_id"] for node in node_runs] == ["start", "end"]
        assert all(node["status"] == "succeeded" for node in node_runs)


def test_tool_arguments_must_be_object() -> None:
    with TestClient(app) as client:
        actor_user_id, _org_id, agent_id, owner_headers = _create_owner_org_agent(
            client, _suffix("wf-tool-args")
        )
        version_id = _create_and_publish_workflow(
            client,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            definition={
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {
                        "id": "tool",
                        "type": "tool",
                        "config": {
                            "tool_id": "missing-tool",
                            "arguments": "not-json-object",
                        },
                    },
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "tool"},
                    {"source": "tool", "target": "end"},
                ],
            },
        )

        run_response = client.post(
            "/workflow-runs",
            json={
                "version_id": version_id,
                "input_data": {"text": "hello"},
                "async_mode": False,
            },
            headers=owner_headers,
        )

        assert run_response.status_code == 200
        run = run_response.json()
        assert run["status"] == "failed"
        assert "Tool arguments must be an object" in run["error_message"]
        node_runs = client.get(
            f"/workflow-runs/{run['run_id']}/nodes",
            params={"actor_user_id": actor_user_id},
        ).json()
        failed_tool = next(node for node in node_runs if node["node_id"] == "tool")
        assert failed_tool["status"] == "failed"
        assert "Tool arguments must be an object" in failed_tool["error_message"]
