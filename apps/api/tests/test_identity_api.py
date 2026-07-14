"""身份与租户 API 测试。"""

import asyncio

from fastapi.testclient import TestClient

from app.database import async_session_factory
from app.models.identity import AuditLogModel
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


def test_identity_writes_create_queryable_structured_audit_events() -> None:
    """Successful organization, team, and member writes leave auditable facts."""

    client = TestClient(app)
    suffix = "api-audit-events"

    owner_response = client.post(
        "/identity/users/register",
        json={
            "email": f"owner-{suffix}@example.com",
            "display_name": "Audit Owner",
            "password": "password123",
        },
    )
    member_response = client.post(
        "/identity/users/register",
        json={
            "email": f"member-{suffix}@example.com",
            "display_name": "Audit Member",
            "password": "password123",
        },
    )
    assert owner_response.status_code == 200
    assert member_response.status_code == 200
    owner_user_id = owner_response.json()["user_id"]
    member_user_id = member_response.json()["user_id"]

    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Audit organization"},
    )
    assert org_response.status_code == 200
    org_id = org_response.json()["org_id"]

    team_response = client.post(
        f"/identity/organizations/{org_id}/teams",
        json={"actor_user_id": owner_user_id, "name": "Audit team"},
    )
    assert team_response.status_code == 200
    team_id = team_response.json()["team_id"]

    added_member_response = client.post(
        f"/identity/organizations/{org_id}/members",
        json={
            "actor_user_id": owner_user_id,
            "target_user_id": member_user_id,
            "role": "developer",
            "team_ids": [team_id],
        },
    )
    assert added_member_response.status_code == 200
    membership_id = added_member_response.json()["membership_id"]

    audit_response = client.get(
        f"/identity/organizations/{org_id}/audit-logs",
        params={"actor_user_id": owner_user_id},
    )
    assert audit_response.status_code == 200

    events = {event["action"]: event for event in audit_response.json()}
    organization_event = events["organization.created"]
    assert organization_event["audit_id"].startswith("aud_")
    assert {key: value for key, value in organization_event.items() if key != "audit_id"} == {
        "org_id": org_id,
        "actor_user_id": owner_user_id,
        "action": "organization.created",
        "target_type": "organization",
        "target_id": org_id,
        "detail": {"name": "Audit organization"},
    }
    assert events["team.created"]["target_id"] == team_id
    assert events["team.created"]["detail"] == {"name": "Audit team"}
    assert events["member.joined"]["target_id"] == membership_id
    assert events["member.joined"]["detail"] == {
        "user_id": member_user_id,
        "role": "developer",
        "team_ids": [team_id],
    }


def test_audit_logs_tolerate_legacy_non_object_details() -> None:
    """Malformed legacy audit details cannot make the read API fail."""

    client = TestClient(app)
    owner_response = client.post(
        "/identity/users/register",
        json={
            "email": "legacy-audit-owner@example.com",
            "display_name": "Legacy Audit Owner",
            "password": "password123",
        },
    )
    assert owner_response.status_code == 200
    owner_user_id = owner_response.json()["user_id"]
    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Legacy audit organization"},
    )
    assert org_response.status_code == 200
    org_id = org_response.json()["org_id"]

    async def add_legacy_logs() -> None:
        async with async_session_factory() as session:
            session.add_all(
                [
                    AuditLogModel(
                        log_id="aud_legacy_malformed",
                        org_id=org_id,
                        actor_user_id=owner_user_id,
                        action="legacy.malformed",
                        resource_type="organization",
                        resource_id=org_id,
                        detail="not-json",
                    ),
                    AuditLogModel(
                        log_id="aud_legacy_scalar",
                        org_id=org_id,
                        actor_user_id=owner_user_id,
                        action="legacy.scalar",
                        resource_type="organization",
                        resource_id=org_id,
                        detail='"scalar"',
                    ),
                    AuditLogModel(
                        log_id="aud_legacy_array",
                        org_id=org_id,
                        actor_user_id=owner_user_id,
                        action="legacy.array",
                        resource_type="organization",
                        resource_id=org_id,
                        detail="[]",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(add_legacy_logs())

    audit_response = client.get(
        f"/identity/organizations/{org_id}/audit-logs",
        params={"actor_user_id": owner_user_id},
    )
    assert audit_response.status_code == 200
    events = {event["action"]: event for event in audit_response.json()}
    assert events["organization.created"]["detail"] == {
        "name": "Legacy audit organization"
    }
    assert events["legacy.malformed"]["detail"] == {}
    assert events["legacy.scalar"]["detail"] == {}
    assert events["legacy.array"]["detail"] == {}


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
