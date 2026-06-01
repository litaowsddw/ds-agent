"""Agent API 测试。"""

from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_agent_api_create_and_read_workspace() -> None:
    """验证 Agent 创建和 Workspace 读取主流程。"""

    client = TestClient(app)
    suffix = "agent-api-main"

    owner_response = client.post(
        "/identity/users/register",
        json={
            "email": f"owner-{suffix}@example.com",
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

    agent_response = client.post(
        "/agents",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "name": "API Agent",
            "description": "通过 API 创建的 Agent",
        },
    )
    assert agent_response.status_code == 200
    agent_id = agent_response.json()["agent_id"]

    workspace_response = client.get(
        f"/agents/{agent_id}/workspace",
        params={"actor_user_id": owner_user_id},
    )
    assert workspace_response.status_code == 200
    assert "AGENTS.md" in workspace_response.json()["files"]


def test_agent_api_rejects_cross_org_workspace_read() -> None:
    """验证其他组织用户不能读取 Agent Workspace。"""

    client = TestClient(app)
    suffix = "agent-api-cross-org"

    alice_response = client.post(
        "/identity/users/register",
        json={
            "email": f"alice-{suffix}@example.com",
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

    agent_response = client.post(
        "/agents",
        json={
            "actor_user_id": alice_user_id,
            "org_id": org_id,
            "name": "私有 Agent",
            "description": "不允许跨组织读取",
        },
    )
    agent_id = agent_response.json()["agent_id"]

    blocked_response = client.get(
        f"/agents/{agent_id}/workspace",
        params={"actor_user_id": bob_user_id},
    )
    assert blocked_response.status_code == 403
