"""Authentication and authorization tests for agent creation."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _register_user(client: TestClient, label: str) -> tuple[str, str]:
    email = f"{label}-{uuid4().hex[:8]}@example.com"
    response = client.post(
        "/identity/users/register",
        json={"email": email, "display_name": label, "password": "password123"},
    )
    assert response.status_code == 200
    return response.json()["user_id"], email


def _login_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/identity/users/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


def test_create_agent_uses_authenticated_identity_and_requires_developer_role(client: TestClient) -> None:
    owner_id, owner_email = _register_user(client, "owner")
    developer_id, developer_email = _register_user(client, "developer")
    _viewer_id, viewer_email = _register_user(client, "viewer")
    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_id, "name": "Agent access control"},
    )
    assert org_response.status_code == 200
    org_id = org_response.json()["org_id"]

    for user_id, role in ((developer_id, "developer"), (_viewer_id, "viewer")):
        response = client.post(
            f"/identity/organizations/{org_id}/members",
            json={
                "actor_user_id": owner_id,
                "target_user_id": user_id,
                "role": role,
                "team_ids": [],
            },
        )
        assert response.status_code == 200

    owner_headers = _login_headers(client, owner_email)
    developer_headers = _login_headers(client, developer_email)
    viewer_headers = _login_headers(client, viewer_email)
    request_data = {"org_id": org_id, "name": "Authorized agent", "description": ""}

    anonymous = client.post("/agents", json={**request_data, "actor_user_id": owner_id})
    assert anonymous.status_code == 401

    forged_viewer = client.post(
        "/agents",
        json={**request_data, "actor_user_id": owner_id, "name": "Forged owner agent"},
        headers=viewer_headers,
    )
    assert forged_viewer.status_code == 403

    developer = client.post(
        "/agents",
        json={**request_data, "actor_user_id": owner_id, "name": "Developer agent"},
        headers=developer_headers,
    )
    assert developer.status_code == 200
    assert developer.json()["created_by"] == developer_id

    admin = client.post(
        "/agents",
        json={**request_data, "actor_user_id": developer_id, "name": "Admin agent"},
        headers=owner_headers,
    )
    assert admin.status_code == 200
    assert admin.json()["created_by"] == owner_id
