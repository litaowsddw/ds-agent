"""Authentication and authorization tests for agent creation."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app
from app.core.auth import register_service_account


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


def test_create_agent_requires_active_org_context_and_matching_team(client: TestClient) -> None:
    owner_id, owner_email = _register_user(client, "scoped-owner")
    org_a = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_id, "name": "Scoped org A"},
    ).json()["org_id"]
    org_b = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_id, "name": "Scoped org B"},
    ).json()["org_id"]
    default_headers = _login_headers(client, owner_email)

    switch_a = client.post(f"/identity/users/switch-org?org_id={org_a}", headers=default_headers)
    assert switch_a.status_code == 200
    org_a_headers = {"Authorization": f"Bearer {switch_a.json()['access_token']}"}
    switch_b = client.post(f"/identity/users/switch-org?org_id={org_b}", headers=default_headers)
    assert switch_b.status_code == 200
    org_b_headers = {"Authorization": f"Bearer {switch_b.json()['access_token']}"}
    team_b = client.post(
        f"/identity/organizations/{org_b}/teams",
        json={"actor_user_id": owner_id, "name": "Foreign team"},
    )
    assert team_b.status_code == 200

    cross_org = client.post(
        "/agents",
        json={"org_id": org_b, "name": "Cross org", "description": ""},
        headers=org_a_headers,
    )
    assert cross_org.status_code == 403

    cross_team = client.post(
        "/agents",
        json={
            "org_id": org_a,
            "team_id": team_b.json()["team_id"],
            "name": "Cross team",
            "description": "",
        },
        headers=org_a_headers,
    )
    assert cross_team.status_code == 403

    switched_org = client.post(
        "/agents",
        json={"org_id": org_b, "name": "Switched org", "description": ""},
        headers=org_b_headers,
    )
    assert switched_org.status_code == 200

    api_key = f"agent-create-{uuid4().hex}"
    register_service_account(api_key, owner_id, org_b)
    api_key_org = client.post(
        "/agents",
        json={"org_id": org_b, "name": "Service agent", "description": ""},
        headers={"X-API-Key": api_key},
    )
    assert api_key_org.status_code == 200
    api_key_cross_org = client.post(
        "/agents",
        json={"org_id": org_a, "name": "Cross org service", "description": ""},
        headers={"X-API-Key": api_key},
    )
    assert api_key_cross_org.status_code == 403
