"""Shared API database harness for every repository test entry point."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

from tests.api_test_harness import cleanup_sqlite_test_database

# This runs before pytest imports test modules, so every FastAPI route sees the
# same isolated database configuration regardless of whether it lives under
# tests/ or apps/api/tests/.
os.environ["AGENTFLOW_PERSISTENCE"] = "0"
_TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / f"agentflow-api-tests-{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DATABASE_PATH.as_posix()}"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
async def reset_api_database() -> None:
    """Give each test an isolated schema on the process-local SQLite database."""

    # These imports must remain inside the fixture: test configuration above
    # needs to be in place before the application's engine is constructed.
    import app.models  # noqa: F401
    from app.database import Base, async_engine

    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield

    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="session", autouse=True)
def cleanup_api_database_after_test_session() -> None:
    """Release the shared test engine and remove its process-local SQLite file."""

    yield

    from app.database import async_engine

    asyncio.run(cleanup_sqlite_test_database(async_engine, _TEST_DATABASE_PATH))
