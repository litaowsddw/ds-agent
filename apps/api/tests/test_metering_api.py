"""Public contracts for tenant-isolated usage queries."""

import importlib.util
import os
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./task4-metering-api.db")


def test_usage_summary_route_is_registered() -> None:
    """The read-only usage surface is available from the application factory."""
    assert importlib.util.find_spec("app.routes.metering") is not None


@pytest.fixture
def usage_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.core.auth import register_service_account
    from app.database import get_db_session
    from app.domain.identity import Membership, OrganizationRole
    from app.routes.metering import router
    from app.services.db.identity_db import membership_db

    async def _session():
        yield SimpleNamespace()

    async def _org_access(_session: object, user_id: str, org_id: str, **_kwargs: object):
        if user_id != "billing-admin" or org_id != "org_1":
            raise ValueError("not a member")
        return Membership(
            membership_id="membership_1",
            org_id="org_1",
            user_id="billing-admin",
            role=OrganizationRole.ADMIN,
        )

    register_service_account("metering-admin-key", "billing-admin", "org_1")
    monkeypatch.setattr(membership_db, "assert_org_access", _org_access)
    app = FastAPI()
    app.include_router(router, prefix="/metering")
    app.dependency_overrides[get_db_session] = _session
    with TestClient(app) as client:
        yield client


def test_usage_summary_requires_authentication(usage_client: TestClient) -> None:
    response = usage_client.get("/metering/usage/summary?org_id=org_1")

    assert response.status_code == 401


def test_usage_summary_groups_by_api_and_model_for_org_billing_admin(
    usage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.db.metering_db import UsageAggregate, metering_db

    async def _aggregate(_session: object, filters: object, group_by: str):
        assert getattr(filters, "org_id") == "org_1"
        assert group_by == "model"
        return [
            UsageAggregate(
                group_by="model",
                group_value="gpt-4o",
                call_count=1,
                unknown_usage_calls=0,
                input_tokens=10,
                output_tokens=2,
                total_tokens=12,
                reasoning_tokens=None,
                cache_read_input_tokens=4,
                cache_write_input_tokens=None,
                model="gpt-4o",
            )
        ]

    monkeypatch.setattr(metering_db, "aggregate_usage", _aggregate)
    response = usage_client.get(
        "/metering/usage/summary?org_id=org_1&group_by=model",
        headers={"X-API-Key": "metering-admin-key"},
    )

    assert response.status_code == 200
    assert response.json()["groups"] == [
        {
            "model": "gpt-4o",
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
            "cache_read_input_tokens": 4,
            "unknown_usage_calls": 0,
            "call_count": 1,
        }
    ]


def test_usage_summary_denies_cross_organization_even_for_authenticated_user(
    usage_client: TestClient,
) -> None:
    response = usage_client.get(
        "/metering/usage/summary?org_id=org_2",
        headers={"X-API-Key": "metering-admin-key"},
    )

    assert response.status_code == 403


def test_usage_summary_denies_org_member_without_billing_permission(
    usage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.domain.identity import Membership, OrganizationRole
    from app.services.db.identity_db import membership_db

    async def _developer_membership(*_args: object, **_kwargs: object):
        return Membership(
            membership_id="membership_developer",
            org_id="org_1",
            user_id="billing-admin",
            role=OrganizationRole.DEVELOPER,
        )

    monkeypatch.setattr(membership_db, "assert_org_access", _developer_membership)
    response = usage_client.get(
        "/metering/usage/summary?org_id=org_1",
        headers={"X-API-Key": "metering-admin-key"},
    )

    assert response.status_code == 403


def test_usage_events_redact_prompt_and_other_organization_data(
    usage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.db.metering_db import metering_db

    async def _list_events(_session: object, filters: object, **_kwargs: object):
        assert getattr(filters, "org_id") == "org_1"
        return [
            SimpleNamespace(
                event_id="evt_1",
                gateway_call_id="call_1",
                org_id="org_1",
                created_at=datetime(2026, 7, 14, tzinfo=UTC),
                source="gateway_api",
                api_name="chat.completions",
                provider_key="openai",
                model="gpt-4o",
                actor_user_id="billing-admin",
                agent_id="agent_1",
                session_id="session_1",
                workflow_id=None,
                workflow_version_id=None,
                workflow_run_id=None,
                workflow_node_id=None,
                dispatch_status="succeeded",
                usage_status="provider_final",
                cache_usage_status="known",
                input_tokens=10,
                output_tokens=2,
                total_tokens=12,
                reasoning_tokens=None,
                cache_read_input_tokens=4,
                cache_write_input_tokens=None,
                prefix_cache_status="eligible",
                prefix_length_bucket="1k-4k",
                dispatched_at=None,
                completed_at=None,
                error_category=None,
                error_code=None,
                error_http_status=None,
                error_retryable=None,
                prompt_preview="a prompt that must never be returned",
                api_key="must-not-leak",
            )
        ]

    monkeypatch.setattr(metering_db, "list_usage_events", _list_events, raising=False)
    response = usage_client.get(
        "/metering/usage/events?org_id=org_1",
        headers={"X-API-Key": "metering-admin-key"},
    )

    assert response.status_code == 200
    assert response.json()["events"][0]["event_id"] == "evt_1"
    assert "prompt_preview" not in response.text
    assert "a prompt that must never be returned" not in response.text
    assert "must-not-leak" not in response.text


def test_usage_by_prefix_returns_only_bucketed_cache_diagnostics(
    usage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.db.metering_db import metering_db

    async def _aggregate_prefix(_session: object, filters: object):
        assert getattr(filters, "org_id") == "org_1"
        return [
            {
                "prefix_cache_status": "eligible",
                "prefix_length_bucket": "1k-4k",
                "call_count": 1,
                "unknown_usage_calls": 0,
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
                "cache_read_input_tokens": 4,
            }
        ]

    monkeypatch.setattr(
        metering_db, "aggregate_prefix_usage", _aggregate_prefix, raising=False
    )
    response = usage_client.get(
        "/metering/usage/by-prefix?org_id=org_1",
        headers={"X-API-Key": "metering-admin-key"},
    )

    assert response.status_code == 200
    group = response.json()["groups"][0]
    assert group["prefix_cache_status"] == "eligible"
    assert group["prefix_length_bucket"] == "1k-4k"
    assert "prefix_hash" not in response.text
