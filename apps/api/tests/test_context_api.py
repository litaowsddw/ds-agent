"""Context API 测试。"""

from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_context_api_assembles_session_context() -> None:
    """验证 Context API 可以从 Session 组装上下文。"""

    client = TestClient(app)
    suffix = "context-api"

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
        json={"creator_user_id": owner_user_id, "name": "Context 组织"},
    )
    org_id = org_response.json()["org_id"]

    agent_response = client.post(
        "/agents",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "name": "Context Agent",
            "description": "用于测试上下文组装",
        },
    )
    agent_id = agent_response.json()["agent_id"]

    session_response = client.post(
        "/sessions",
        json={"actor_user_id": owner_user_id, "agent_id": agent_id, "queue_mode": "queue"},
    )
    session_id = session_response.json()["session_id"]

    client.post(
        f"/sessions/{session_id}/messages",
        json={"actor_user_id": owner_user_id, "role": "user", "content": "请记住我的偏好。"},
    )

    context_response = client.get(
        f"/context/sessions/{session_id}/assemble",
        params={"actor_user_id": owner_user_id, "current_input": "继续刚才的话题"},
    )

    assert context_response.status_code == 200
    section_names = [section["name"] for section in context_response.json()["sections"]]
    assert "workspace" in section_names
    assert "memories" in section_names
    assert "append_only_messages" in section_names
    assert "current_input" in section_names
