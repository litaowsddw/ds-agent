"""Contract tests for public, secret-protected Workflow webhook triggers."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.routes import workflow_runs


def _suffix() -> str:
    return uuid4().hex[:10]


def _owner_org_agent(client: TestClient) -> tuple[str, str, dict[str, str]]:
    suffix = _suffix()
    email = f"webhook-owner-{suffix}@example.com"
    user_id = client.post(
        "/identity/users/register",
        json={"email": email, "display_name": "Owner", "password": "password123"},
    ).json()["user_id"]
    org_id = client.post(
        "/identity/organizations", json={"creator_user_id": user_id, "name": "Webhook Org"}
    ).json()["org_id"]
    login = client.post("/identity/users/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']['access_token']}"}
    agent = client.post(
        "/agents",
        headers=headers,
        json={
            "actor_user_id": user_id,
            "org_id": org_id,
            "name": "Webhook Agent",
            "description": "",
        },
    )
    assert agent.status_code == 200
    return user_id, agent.json()["agent_id"], headers


def _published_version(
    client: TestClient, user_id: str, agent_id: str, headers: dict[str, str]
) -> str:
    workflow = client.post(
        "/workflows",
        headers=headers,
        json={
            "actor_user_id": user_id,
            "agent_id": agent_id,
            "name": "Webhook Workflow",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [{"source": "start", "target": "end"}],
            },
        },
    )
    assert workflow.status_code == 200
    version = client.post(
        f"/workflows/{workflow.json()['workflow_id']}/publish",
        headers=headers,
        json={"actor_user_id": user_id},
    )
    assert version.status_code == 200
    return version.json()["version_id"]


def _create_trigger(
    client: TestClient, version_id: str, headers: dict[str, str]
) -> dict[str, object]:
    response = client.post("/workflow-triggers", headers=headers, json={"version_id": version_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_webhook_secret_is_creation_only_and_delivery_is_idempotent(monkeypatch) -> None:
    async def _queue_run(_run) -> None:
        return None

    monkeypatch.setattr(workflow_runs, "_submit_async_run", _queue_run)

    with TestClient(app) as client:
        user_id, agent_id, auth_headers = _owner_org_agent(client)
        version_id = _published_version(client, user_id, agent_id, auth_headers)
        trigger = _create_trigger(client, version_id, auth_headers)
        trigger_id = str(trigger["trigger_id"])
        secret = str(trigger["secret"])

        assert secret not in str({key: value for key, value in trigger.items() if key != "secret"})
        fetched = client.get(f"/workflow-triggers/{trigger_id}", headers=auth_headers)
        assert fetched.status_code == 200
        assert "secret" not in fetched.json()
        assert fetched.json()["invoke_path"] == f"/webhooks/workflows/{trigger_id}"

        headers = {"X-Webhook-Secret": secret, "Idempotency-Key": "event-00000001"}
        first = client.post(
            f"/webhooks/workflows/{trigger_id}", headers=headers, json={"ticket": "T-1"}
        )
        assert first.status_code == 202, first.text
        body = first.json()
        assert body["status"] == "pending"
        assert body["idempotent_replay"] is False

        second = client.post(
            f"/webhooks/workflows/{trigger_id}", headers=headers, json={"ticket": "changed"}
        )
        assert second.status_code == 202
        assert second.json()["run_id"] == body["run_id"]
        assert second.json()["idempotent_replay"] is True

        run = client.get(f"/workflow-runs/{body['run_id']}", params={"actor_user_id": user_id})
        assert run.status_code == 200
        assert run.json()["input_data"] == {"ticket": "T-1"}

        logs = client.get(
            f"/identity/organizations/{run.json()['org_id']}/audit-logs",
            params={"actor_user_id": user_id},
        )
        assert logs.status_code == 200
        assert secret not in logs.text


def test_webhook_rejects_invalid_secret_oversize_and_disabled_trigger(monkeypatch) -> None:
    async def _queue_run(_run) -> None:
        return None

    monkeypatch.setattr(workflow_runs, "_submit_async_run", _queue_run)

    with TestClient(app) as client:
        user_id, agent_id, auth_headers = _owner_org_agent(client)
        version_id = _published_version(client, user_id, agent_id, auth_headers)
        trigger = _create_trigger(client, version_id, auth_headers)
        trigger_id = str(trigger["trigger_id"])
        secret = str(trigger["secret"])
        path = f"/webhooks/workflows/{trigger_id}"

        no_secret = client.post(path, headers={"Idempotency-Key": "event-00000002"}, json={})
        assert no_secret.status_code == 401
        invalid_key = client.post(path, headers={"X-Webhook-Secret": secret}, json={})
        assert invalid_key.status_code == 400

        oversized = client.post(
            path,
            headers={"X-Webhook-Secret": secret, "Idempotency-Key": "event-00000003"},
            json={"payload": "x" * (128 * 1024)},
        )
        assert oversized.status_code == 413

        disabled = client.post(f"/workflow-triggers/{trigger_id}/disable", headers=auth_headers)
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        blocked = client.post(
            path,
            headers={"X-Webhook-Secret": secret, "Idempotency-Key": "event-00000004"},
            json={},
        )
        assert blocked.status_code == 401


def test_webhook_trigger_is_unique_per_immutable_version() -> None:
    with TestClient(app) as client:
        user_id, agent_id, auth_headers = _owner_org_agent(client)
        version_id = _published_version(client, user_id, agent_id, auth_headers)
        _create_trigger(client, version_id, auth_headers)
        duplicate = client.post(
            "/workflow-triggers", headers=auth_headers, json={"version_id": version_id}
        )
        assert duplicate.status_code == 409


def test_webhook_trigger_management_requires_same_org_developer() -> None:
    with TestClient(app) as client:
        user_id, agent_id, auth_headers = _owner_org_agent(client)
        version_id = _published_version(client, user_id, agent_id, auth_headers)
        stranger_email = f"webhook-stranger-{_suffix()}@example.com"
        register = client.post(
            "/identity/users/register",
            json={
                "email": stranger_email,
                "display_name": "Stranger",
                "password": "password123",
            },
        )
        assert register.status_code == 200
        login = client.post(
            "/identity/users/login",
            json={"email": stranger_email, "password": "password123"},
        )
        assert login.status_code == 200
        stranger_headers = {"Authorization": f"Bearer {login.json()['token']['access_token']}"}

        denied = client.post(
            "/workflow-triggers", headers=stranger_headers, json={"version_id": version_id}
        )
        assert denied.status_code == 403
