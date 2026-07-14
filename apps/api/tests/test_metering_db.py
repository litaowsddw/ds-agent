"""Durable usage-event persistence tests."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
from sqlalchemy.ext import asyncio as sqlalchemy_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


_real_create_async_engine = sqlalchemy_asyncio.create_async_engine


def _create_test_engine(url: str, *args: object, **kwargs: object):
    """Allow the application's MySQL-oriented database module to load under SQLite."""
    kwargs.pop("pool_size", None)
    kwargs.pop("max_overflow", None)
    kwargs.pop("pool_recycle", None)
    return _real_create_async_engine(url, *args, **kwargs)


sqlalchemy_asyncio.create_async_engine = _create_test_engine

from app.database import Base
from app.models.metering import LLMUsageEventModel, ModelPriceModel
from app.services.db.metering_db import UsageEventInput, UsageFilters, metering_db


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[LLMUsageEventModel.__table__, ModelPriceModel.__table__],
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db_session:
            yield db_session
    finally:
        await engine.dispose()


def reported_event(
    org_id: str,
    gateway_call_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int | None = None,
) -> UsageEventInput:
    return UsageEventInput(
        gateway_call_id=gateway_call_id,
        org_id=org_id,
        source="gateway_api",
        api_name="chat.completions",
        provider_key="openai",
        model="gpt-4o",
        dispatch_status="completed",
        usage_status="reported",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_usage_status="reported",
        cache_read_input_tokens=cache_read_input_tokens,
    )


def unavailable_event(org_id: str, gateway_call_id: str) -> UsageEventInput:
    return UsageEventInput(
        gateway_call_id=gateway_call_id,
        org_id=org_id,
        source="gateway_api",
        api_name="chat.completions",
        provider_key="openai",
        model="gpt-4o",
        dispatch_status="dispatched",
        usage_status="unavailable",
        input_tokens=None,
        output_tokens=None,
        cache_usage_status="unknown",
    )


def test_record_event_is_idempotent_and_preserves_unknown_usage() -> None:
    async def case() -> None:
        async with session_scope() as session:
            event = unavailable_event("org_1", "llm_call_1")

            first = await metering_db.record_event(session, event)
            second = await metering_db.record_event(session, event)

            assert first.event_id == second.event_id
            assert first.input_tokens is None
            assert first.cache_read_input_tokens is None

    asyncio.run(case())


def test_record_event_never_overwrites_reported_usage_on_replay() -> None:
    async def case() -> None:
        async with session_scope() as session:
            first = await metering_db.record_event(
                session, reported_event("org_1", "llm_call_1", 12, 8, 5)
            )
            replay = await metering_db.record_event(
                session, reported_event("org_1", "llm_call_1", 99, 77, 66)
            )

            assert replay.event_id == first.event_id
            assert replay.input_tokens == 12
            assert replay.output_tokens == 8
            assert replay.cache_read_input_tokens == 5

    asyncio.run(case())


def test_aggregate_usage_groups_only_known_token_values() -> None:
    async def case() -> None:
        async with session_scope() as session:
            await metering_db.record_event(
                session, reported_event("org_1", "llm_call_1", 12, 8, 5)
            )
            await metering_db.record_event(session, unavailable_event("org_1", "llm_call_2"))

            rows = await metering_db.aggregate_usage(session, UsageFilters(org_id="org_1"), "model")

            assert len(rows) == 1
            assert rows[0].model == "gpt-4o"
            assert rows[0].input_tokens == 12
            assert rows[0].output_tokens == 8
            assert rows[0].cache_read_input_tokens == 5
            assert rows[0].unknown_usage_calls == 1

    asyncio.run(case())


def test_aggregate_usage_filters_and_supported_dimensions() -> None:
    async def case() -> None:
        async with session_scope() as session:
            await metering_db.record_event(
                session, reported_event("org_1", "llm_call_1", 12, 8)
            )
            await metering_db.record_event(
                session, reported_event("org_1", "llm_call_2", 20, 10)
            )

            rows = await metering_db.aggregate_usage(
                session,
                UsageFilters(
                    org_id="org_1",
                    provider_key="openai",
                ),
                "provider_key",
            )

            assert len(rows) == 1
            assert rows[0].provider_key == "openai"
            assert rows[0].input_tokens == 32
            assert rows[0].call_count == 2

    asyncio.run(case())


def test_usage_event_rejects_updates_across_sessions() -> None:
    async def case() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.create_all,
                tables=[LLMUsageEventModel.__table__, ModelPriceModel.__table__],
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as write_session:
                persisted = await metering_db.record_event(
                    write_session, reported_event("org_1", "llm_call_immutable", 12, 8)
                )
                event_id = persisted.event_id
                original_created_at = persisted.created_at.replace(tzinfo=None)
                await write_session.commit()

            for field, value in (
                ("input_tokens", 99),
                ("created_at", datetime(2026, 7, 1, tzinfo=timezone.utc)),
            ):
                async with factory() as update_session:
                    persisted = await update_session.get(LLMUsageEventModel, event_id)
                    assert persisted is not None
                    setattr(persisted, field, value)

                    with pytest.raises(ValueError, match="immutable"):
                        await update_session.flush()
                    await update_session.rollback()

                async with factory() as verify_session:
                    reloaded = await verify_session.get(LLMUsageEventModel, event_id)
                    assert reloaded is not None
                    assert reloaded.input_tokens == 12
                    assert reloaded.created_at == original_created_at
        finally:
            await engine.dispose()

    asyncio.run(case())
