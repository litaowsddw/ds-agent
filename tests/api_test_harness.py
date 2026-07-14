"""Test-only cleanup helpers for the file-backed SQLite API database."""

import asyncio
from pathlib import Path
from typing import Protocol


class DisposableAsyncEngine(Protocol):
    """The narrow engine contract required by the test cleanup hook."""

    async def dispose(self) -> None: ...


async def cleanup_sqlite_test_database(
    engine: DisposableAsyncEngine, database_path: Path
) -> None:
    """Dispose DB connections before removing a file-backed SQLite test database."""

    await engine.dispose()
    for attempt in range(3):
        try:
            database_path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == 2:
                raise
            # Windows may release the final aiosqlite handle one event-loop
            # turn after dispose().  Retrying keeps teardown deterministic.
            await asyncio.sleep(0.05)
