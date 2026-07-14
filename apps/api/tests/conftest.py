"""API 测试配置。"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 测试环境关闭本地状态文件，确保每次测试都从干净的内存 Store 开始。
os.environ["AGENTFLOW_PERSISTENCE"] = "0"

# Set this before any application import.  A file database is deliberately
# used instead of ``:memory:`` because the application and TestClient can use
# separate connections (and separate event loops).
_TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / f"agentflow-api-tests-{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DATABASE_PATH.as_posix()}"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
async def reset_api_database() -> None:
    """Give every API test a fresh schema on the process-local SQLite file."""

    # Imports intentionally happen after DATABASE_URL is configured above.
    import app.models  # noqa: F401
    from app.database import Base, async_engine

    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield

    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
