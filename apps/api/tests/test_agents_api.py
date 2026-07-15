"""Agent API 测试。"""

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


def _login_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/identity/users/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


def test_agent_api_create_and_read_workspace(client: TestClient) -> None:
    """验证 Agent 创建和 Workspace 读取主流程。"""

    suffix = _suffix("agent-api-main")

    owner_email = f"owner-{suffix}@example.com"
    owner_response = client.post(
        "/identity/users/register",
        json={
            "email": owner_email,
            "display_name": "Owner",
            "password": "password123",
        },
    )
    owner_user_id = owner_response.json()["user_id"]

    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Agent API 组织"},
    )
    org_id = org_response.json()["org_id"]
    owner_headers = _login_headers(client, owner_email)

    agent_response = client.post(
        "/agents",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "name": "API Agent",
            "description": "通过 API 创建的 Agent",
        },
        headers=owner_headers,
    )
    assert agent_response.status_code == 200
    agent_id = agent_response.json()["agent_id"]

    workspace_response = client.get(
        f"/agents/{agent_id}/workspace",
        params={"actor_user_id": owner_user_id},
    )
    assert workspace_response.status_code == 200
    assert "AGENTS.md" in workspace_response.json()["files"]


def test_agent_api_rejects_cross_org_workspace_read(client: TestClient) -> None:
    """验证其他组织用户不能读取 Agent Workspace。"""

    suffix = _suffix("agent-api-cross")

    alice_email = f"alice-{suffix}@example.com"
    alice_response = client.post(
        "/identity/users/register",
        json={
            "email": alice_email,
            "display_name": "Alice",
            "password": "password123",
        },
    )
    bob_response = client.post(
        "/identity/users/register",
        json={
            "email": f"bob-{suffix}@example.com",
            "display_name": "Bob",
            "password": "password123",
        },
    )
    alice_user_id = alice_response.json()["user_id"]
    bob_user_id = bob_response.json()["user_id"]

    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": alice_user_id, "name": "Alice Agent 组织"},
    )
    org_id = org_response.json()["org_id"]
    alice_headers = _login_headers(client, alice_email)

    agent_response = client.post(
        "/agents",
        json={
            "actor_user_id": alice_user_id,
            "org_id": org_id,
            "name": "私有 Agent",
            "description": "不允许跨组织读取",
        },
        headers=alice_headers,
    )
    agent_id = agent_response.json()["agent_id"]

    blocked_response = client.get(
        f"/agents/{agent_id}/workspace",
        params={"actor_user_id": bob_user_id},
    )
    assert blocked_response.status_code == 403


def test_agent_default_workflow_starts_empty(client: TestClient) -> None:
    suffix = _suffix("agent-wf-empty")
    owner_email = f"owner-{suffix}@example.com"
    owner_response = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "Owner", "password": "password123"},
    )
    owner_user_id = owner_response.json()["user_id"]
    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Default Workflow Org"},
    )
    org_id = org_response.json()["org_id"]
    owner_headers = _login_headers(client, owner_email)

    agent_response = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": "Autonomous Agent", "description": ""},
        headers=owner_headers,
    )

    assert agent_response.status_code == 200
    assert agent_response.json()["default_workflow_id"] is None


def test_agent_update_rejects_default_workflow_from_other_agent(client: TestClient) -> None:
    suffix = _suffix("agent-wf-cross")
    owner_email = f"owner-{suffix}@example.com"
    owner_response = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "Owner", "password": "password123"},
    )
    owner_user_id = owner_response.json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Cross Workflow Org"},
    ).json()["org_id"]
    owner_headers = _login_headers(client, owner_email)
    agent_a = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": "Agent A", "description": ""},
        headers=owner_headers,
    ).json()
    agent_b = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": "Agent B", "description": ""},
        headers=owner_headers,
    ).json()
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_b["agent_id"],
            "name": "Agent B Workflow",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [{"id": "start", "type": "start", "config": {}}, {"id": "end", "type": "end", "config": {}}],
                "edges": [{"source": "start", "target": "end"}],
            },
        },
    ).json()
    client.post(f"/workflows/{workflow['workflow_id']}/publish", json={"actor_user_id": owner_user_id})

    update_response = client.put(
        f"/agents/{agent_a['agent_id']}",
        json={
            "actor_user_id": owner_user_id,
            "name": "Agent A",
            "description": "",
            "default_workflow_id": workflow["workflow_id"],
        },
    )

    assert update_response.status_code == 400
    assert "默认 Workflow 必须属于当前 Agent" in update_response.text


def test_agent_update_accepts_own_published_default_workflow(client: TestClient) -> None:
    suffix = _suffix("agent-wf-own")
    owner_email = f"owner-{suffix}@example.com"
    owner_response = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "Owner", "password": "password123"},
    )
    owner_user_id = owner_response.json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Own Workflow Org"},
    ).json()["org_id"]
    owner_headers = _login_headers(client, owner_email)
    agent = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": "Agent", "description": ""},
        headers=owner_headers,
    ).json()
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent["agent_id"],
            "name": "Default Workflow",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [{"id": "start", "type": "start", "config": {}}, {"id": "end", "type": "end", "config": {}}],
                "edges": [{"source": "start", "target": "end"}],
            },
        },
    ).json()
    client.post(f"/workflows/{workflow['workflow_id']}/publish", json={"actor_user_id": owner_user_id})

    update_response = client.put(
        f"/agents/{agent['agent_id']}",
        json={
            "actor_user_id": owner_user_id,
            "name": "Agent",
            "description": "",
            "default_workflow_id": workflow["workflow_id"],
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["default_workflow_id"] == workflow["workflow_id"]
