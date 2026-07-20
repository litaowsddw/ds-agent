"""Workflow version audit and safe draft-restore API contracts."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import app


def _suffix() -> str:
    return uuid4().hex[:8]


def _owner_and_agent(client: TestClient) -> tuple[str, str]:
    suffix = _suffix()
    email = f"workflow-audit-{suffix}@example.com"
    user_id = client.post(
        "/identity/users/register",
        json={"email": email, "display_name": "Workflow owner", "password": "password123"},
    ).json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": user_id, "name": f"Audit Org {suffix}"},
    ).json()["org_id"]
    login = client.post(
        "/identity/users/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    agent_id = client.post(
        "/agents",
        json={
            "actor_user_id": user_id,
            "org_id": org_id,
            "name": "Workflow Agent",
            "description": "",
        },
        headers={"Authorization": f"Bearer {login.json()['token']['access_token']}"},
    ).json()["agent_id"]
    return user_id, agent_id


def _definition(label: str) -> dict[str, object]:
    return {
        "version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "end", "type": "end", "config": {"label": label}},
        ],
        "edges": [{"source": "start", "target": "end"}],
    }


def _create_workflow(client: TestClient, user_id: str, agent_id: str, definition: dict[str, object]) -> str:
    response = client.post(
        "/workflows",
        json={
            "actor_user_id": user_id,
            "agent_id": agent_id,
            "name": "Audited workflow",
            "description": "",
            "draft_definition": definition,
        },
    )
    assert response.status_code == 200
    return response.json()["workflow_id"]


def _publish(client: TestClient, workflow_id: str, user_id: str, release_note: str) -> dict[str, object]:
    response = client.post(
        f"/workflows/{workflow_id}/publish",
        json={"actor_user_id": user_id, "release_note": release_note},
    )
    assert response.status_code == 200
    return response.json()


def test_published_version_keeps_audit_note_and_can_restore_a_draft() -> None:
    with TestClient(app) as client:
        user_id, agent_id = _owner_and_agent(client)
        original = _definition("original")
        workflow_id = _create_workflow(client, user_id, agent_id, original)
        version = _publish(client, workflow_id, user_id, "Approved for customer-support rollout")

        assert version["release_note"] == "Approved for customer-support rollout"
        assert version["created_by"] == user_id
        assert version["created_at"]

        changed = _definition("unpublished change")
        update = client.put(
            f"/workflows/{workflow_id}/draft",
            json={"actor_user_id": user_id, "draft_definition": changed},
        )
        assert update.status_code == 200

        restored = client.post(
            f"/workflows/{workflow_id}/versions/{version['version_id']}/restore-draft",
            json={"actor_user_id": user_id},
        )
        assert restored.status_code == 200
        assert restored.json()["draft_definition"] == original
        # Restoring a snapshot prepares a draft only; it never changes live traffic.
        assert restored.json()["published_version_id"] == version["version_id"]

        listed = client.get(
            f"/workflows/{workflow_id}/versions",
            params={"actor_user_id": user_id},
        )
        assert listed.status_code == 200
        assert listed.json() == [version]


def test_restore_rejects_a_version_from_another_workflow() -> None:
    with TestClient(app) as client:
        user_id, agent_id = _owner_and_agent(client)
        first_workflow_id = _create_workflow(client, user_id, agent_id, _definition("first"))
        second_workflow_id = _create_workflow(client, user_id, agent_id, _definition("second"))
        second_version = _publish(client, second_workflow_id, user_id, "Second workflow release")

        response = client.post(
            f"/workflows/{first_workflow_id}/versions/{second_version['version_id']}/restore-draft",
            json={"actor_user_id": user_id},
        )

        assert response.status_code == 400
        assert "不属于当前" in response.json()["detail"]
