"""Integration contract from a Gateway attempt to an authorized org summary.

The test deliberately uses a local SQLite database and a fake provider. It
verifies the real Gateway recorder and aggregate query without requiring a
network provider or a shared MySQL service.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from types import ModuleType

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


# Route and model imports create the application engine. This scenario supplies
# a local driver before those imports so it remains runnable without MySQL.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./metering-usage-flow.db")


@dataclass
class _AllowingLimiter:
    async def require(self, **_kwargs: object) -> None:
        return None


class _ReportedUsageProvider:
    def generate(self, request: object) -> object:
        from app.gateway.llm import LLMCallResponse

        return LLMCallResponse(
            text="ok",
            provider=str(getattr(request, "provider")),
            model=str(getattr(request, "model")),
            usage={"prompt_tokens": 8, "completion_tokens": 4},
        )


class _RateLimitExceeded(RuntimeError):
    pass


def _install_rate_limiter_stub() -> None:
    """Keep this local integration test independent of an installed Redis client."""

    if "apps.api.app.gateway.rate_limiter" in sys.modules:
        return
    module = ModuleType("apps.api.app.gateway.rate_limiter")
    module.HybridRateLimiter = _AllowingLimiter
    module.RateLimitExceeded = _RateLimitExceeded
    module.rate_limiter = _AllowingLimiter()
    sys.modules[module.__name__] = module


def test_authenticated_gateway_attempt_appears_once_in_org_usage_summary(
    tmp_path, monkeypatch
) -> None:
    """A persisted Gateway attempt is visible once to its billing administrator."""

    asyncio.run(_run_usage_flow(tmp_path, monkeypatch))


async def _run_usage_flow(tmp_path, monkeypatch) -> None:
    _install_rate_limiter_stub()
    from app.core.auth import register_service_account
    from app.database import Base, get_db_session
    from app.domain.identity import Membership, OrganizationRole
    from app.gateway.llm import LLMCallRequest, LLMGateway
    from app.routes.metering import router as metering_router
    from app.services.db.identity_db import membership_db
    from app.services.metering import SessionUsageRecorder, UsageContext

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'metering-flow.db'}"
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        gateway = LLMGateway(
            providers={"mock": _ReportedUsageProvider()},
            limiter=_AllowingLimiter(),
            usage_recorder=SessionUsageRecorder(session),
        )
        response = await gateway.generate(
            LLMCallRequest(
                provider="mock",
                model="mock-model",
                prompt="summarize",
                metadata=UsageContext(
                    org_id="org_1",
                    actor_user_id="billing-admin",
                    source="gateway_api",
                    api_name="chat.completions",
                ).as_metadata(),
            )
        )
        assert response.usage == {"prompt_tokens": 8, "completion_tokens": 4}
        await session.commit()

    async def _session():
        async with sessions() as session:
            yield session

    async def _org_access(_session: object, user_id: str, org_id: str, **_kwargs: object):
        assert user_id == "billing-admin"
        assert org_id == "org_1"
        return Membership(
            membership_id="membership_1",
            org_id=org_id,
            user_id=user_id,
            role=OrganizationRole.ADMIN,
        )

    register_service_account("metering-flow-key", "billing-admin", "org_1")
    monkeypatch.setattr(membership_db, "assert_org_access", _org_access)
    app = FastAPI()
    app.include_router(metering_router, prefix="/metering")
    app.dependency_overrides[get_db_session] = _session
    with TestClient(app) as client:
        summary = client.get(
            "/metering/usage/summary?group_by=api",
            headers={"X-API-Key": "metering-flow-key"},
        )

    assert summary.status_code == 200
    groups = summary.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["api_name"] == "chat.completions"
    assert groups[0]["call_count"] == 1
    assert groups[0]["input_tokens"] == 8
    assert groups[0]["output_tokens"] == 4
    assert groups[0]["total_tokens"] == 12

    await engine.dispose()
