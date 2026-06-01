"""身份与租户 API 测试。"""

from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_identity_api_main_flow() -> None:
    """验证注册、创建组织、创建群组、查看审计日志的主流程。"""

    # client 是 FastAPI 测试客户端。
    client = TestClient(app)

    # suffix 用于避免进程内存存储里的邮箱重复。
    suffix = "api-main-flow"

    owner_response = client.post(
        "/identity/users/register",
        json={
            "email": f"owner-{suffix}@example.com",
            "display_name": "Owner",
            "password": "password123",
        },
    )
    assert owner_response.status_code == 200
    owner_user_id = owner_response.json()["user_id"]

    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "AgentFlow 组织"},
    )
    assert org_response.status_code == 200
    org_id = org_response.json()["org_id"]

    team_response = client.post(
        f"/identity/organizations/{org_id}/teams",
        json={"actor_user_id": owner_user_id, "name": "Runtime 团队"},
    )
    assert team_response.status_code == 200
    assert team_response.json()["org_id"] == org_id

    audit_response = client.get(
        f"/identity/organizations/{org_id}/audit-logs",
        params={"actor_user_id": owner_user_id},
    )
    assert audit_response.status_code == 200
    assert len(audit_response.json()) >= 2


def test_identity_api_rejects_cross_org_access() -> None:
    """验证跨组织访问会被拒绝。"""

    client = TestClient(app)
    suffix = "api-cross-org"

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
        json={"creator_user_id": alice_user_id, "name": "Alice 私有组织"},
    )
    org_id = org_response.json()["org_id"]

    blocked_response = client.get(
        f"/identity/organizations/{org_id}/teams",
        params={"actor_user_id": bob_user_id},
    )
    assert blocked_response.status_code == 403
