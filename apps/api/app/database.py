"""数据库配置与会话管理。

使用 SQLAlchemy 2.x 异步引擎 + MySQL 8.0。
同时提供同步引擎供 Worker 进程使用。
"""

import os

from sqlalchemy import create_engine as sync_create_engine
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# 数据库连接配置 - 从环境变量读取
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://agentflow:agentflow@localhost:3306/agentflow?charset=utf8mb4",
)

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# 同步数据库 URL（供 Worker 使用）
SYNC_DATABASE_URL = (
    DATABASE_URL.replace("+aiomysql", "+pymysql")
    if not IS_SQLITE
    else DATABASE_URL.replace("+aiosqlite", "")
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""
    pass


# ── 异步引擎（API 服务使用）──

_async_engine_options = {"echo": False}
if not IS_SQLITE:
    _async_engine_options.update(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

async_engine = create_async_engine(DATABASE_URL, **_async_engine_options)

async_session_factory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncSession:
    """获取数据库会话（用于 FastAPI 依赖注入）。"""
    async with async_session_factory() as session:
        yield session


# ── 同步引擎（Worker 进程使用）──

try:
    _sync_engine_options = {"echo": False}
    if not IS_SQLITE:
        _sync_engine_options.update(
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    engine = sync_create_engine(SYNC_DATABASE_URL, **_sync_engine_options)
except Exception:
    # pymysql 未安装时降级
    engine = None


# ── 数据库初始化 ──

async def init_db() -> None:
    """初始化数据库 - 创建所有表。"""
    # 确保所有模型被导入
    import app.models  # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_session_message_meta_info_column)
        await conn.run_sync(_ensure_mcp_credentials_column)
        await conn.run_sync(_ensure_agent_context_token_limit_column)


def _ensure_session_message_meta_info_column(connection) -> None:
    """Backfill lightweight schema changes for create_all-managed local DBs."""
    inspector = inspect(connection)
    if "session_messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("session_messages")}
    if "meta_info" in columns:
        return
    connection.execute(text("ALTER TABLE session_messages ADD COLUMN meta_info TEXT"))
    connection.execute(text("UPDATE session_messages SET meta_info = '{}' WHERE meta_info IS NULL"))


def _ensure_mcp_credentials_column(connection) -> None:
    """Backfill encrypted connection credentials for existing deployments."""
    inspector = inspect(connection)
    if "mcp_servers" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("mcp_servers")}
    if "credentials_encrypted" not in columns:
        connection.execute(text("ALTER TABLE mcp_servers ADD COLUMN credentials_encrypted TEXT"))
        connection.execute(text("UPDATE mcp_servers SET credentials_encrypted = '' WHERE credentials_encrypted IS NULL"))


def _ensure_agent_context_token_limit_column(connection) -> None:
    """Backfill the per-agent memory compaction threshold for existing deployments."""
    inspector = inspect(connection)
    if "agents" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("agents")}
    if "context_token_limit" not in columns:
        connection.execute(text("ALTER TABLE agents ADD COLUMN context_token_limit INTEGER"))
