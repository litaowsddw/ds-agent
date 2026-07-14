"""Regression tests for the repository-wide API SQLite harness."""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.api_test_harness import cleanup_sqlite_test_database


class TrackingAsyncEngine:
    """Wrap a real engine so the cleanup contract can be asserted directly."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True
        await self._engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_disposes_engine_before_removing_sqlite_file(tmp_path: Path) -> None:
    """Session cleanup must release Windows file handles before unlinking the DB."""

    database_path = tmp_path / "api-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    tracked_engine = TrackingAsyncEngine(engine)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE cleanup_probe (id INTEGER PRIMARY KEY)"))

    assert database_path.exists()

    await cleanup_sqlite_test_database(tracked_engine, database_path)

    assert tracked_engine.disposed is True
    assert not database_path.exists()


def test_pytest_session_teardown_removes_its_process_sqlite_file() -> None:
    """The real pytest session finalizer must clean the child process database."""

    repository_root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api_integration.py::TestJWTAuthFlow::test_register_route_uses_the_shared_sqlite_harness",
            "-q",
        ],
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output, _ = process.communicate(timeout=60)
    child_database_path = Path(tempfile.gettempdir()) / f"agentflow-api-tests-{process.pid}.db"

    assert process.returncode == 0, output
    assert not child_database_path.exists(), output
