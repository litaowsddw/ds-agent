"""Session 与消息数据库服务。

替换 session_store.py 的内存实现，使用 SQLAlchemy 异步操作 MySQL。
"""

from datetime import datetime
import json
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import SessionModel, SessionMessageModel
from app.services.db.base import BaseDBService


class SessionDBService(BaseDBService[SessionModel]):
    """Session 数据库服务。"""

    def __init__(self) -> None:
        super().__init__(SessionModel)

    async def create_session(
        self,
        session: AsyncSession,
        session_id: str,
        org_id: str,
        agent_id: str,
        user_id: str,
        queue_mode: str = "queue",
    ) -> SessionModel:
        """创建会话。"""
        s = SessionModel(
            session_id=session_id,
            org_id=org_id,
            agent_id=agent_id,
            user_id=user_id,
            queue_mode=queue_mode,
            status="idle",
        )
        session.add(s)
        await session.flush()
        return s

    async def get_session_required(self, session: AsyncSession, session_id: str) -> SessionModel:
        """获取会话，不存在则抛出 ValueError。"""
        return await self.get_by_id_required(session, session_id, "session_id")

    async def list_agent_sessions(
        self,
        session: AsyncSession,
        agent_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[SessionModel], int]:
        """列出 Agent 的会话。"""
        return await self.list_paginated(
            session, offset=offset, limit=limit, agent_id=agent_id
        )

    async def set_status(
        self, session: AsyncSession, session_id: str, status: str
    ) -> SessionModel:
        """更新会话状态。"""
        s = await self.get_session_required(session, session_id)
        s.status = status
        s.updated_at = datetime.utcnow()
        await session.flush()
        return s

    async def compact_session(
        self, session: AsyncSession, session_id: str, summary: str
    ) -> SessionModel:
        """写入会话压缩摘要。"""
        s = await self.get_session_required(session, session_id)
        s.compact_summary = summary
        s.updated_at = datetime.utcnow()
        await session.flush()
        return s


class SessionMessageDBService(BaseDBService[SessionMessageModel]):
    """Session 消息数据库服务。"""

    def __init__(self) -> None:
        super().__init__(SessionMessageModel)

    async def append_message(
        self,
        session: AsyncSession,
        message_id: str,
        session_id: str,
        org_id: str,
        agent_id: str,
        role: str,
        content: str,
        estimated_tokens: int = 0,
        meta_info: dict[str, Any] | None = None,
    ) -> SessionMessageModel:
        """追加消息（append-only）。"""
        # 计算序号
        count_stmt = select(func.count()).select_from(SessionMessageModel).where(
            SessionMessageModel.session_id == session_id
        )
        result = await session.execute(count_stmt)
        sequence = (result.scalar() or 0) + 1

        message = SessionMessageModel(
            message_id=message_id,
            session_id=session_id,
            org_id=org_id,
            agent_id=agent_id,
            role=role,
            content=content,
            sequence=sequence,
            estimated_tokens=estimated_tokens,
            meta_info=json.dumps(meta_info or {}, ensure_ascii=False, sort_keys=True),
        )
        session.add(message)
        await session.flush()
        return message

    async def list_session_messages(
        self,
        session: AsyncSession,
        session_id: str,
        offset: int = 0,
        limit: int = 200,
    ) -> list[SessionMessageModel]:
        """按 append-only 顺序列出会话消息。"""
        stmt = (
            select(SessionMessageModel)
            .where(SessionMessageModel.session_id == session_id)
            .order_by(SessionMessageModel.sequence)
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_uncompacted_messages(
        self,
        session: AsyncSession,
        session_id: str,
        limit: int = 20,
    ) -> list[SessionMessageModel]:
        """List recent messages that have not been folded into the compact summary."""
        stmt = (
            select(SessionMessageModel)
            .where(
                SessionMessageModel.session_id == session_id,
                SessionMessageModel.compacted == False,
            )
            .order_by(SessionMessageModel.sequence.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def mark_compacted(
        self, session: AsyncSession, session_id: str
    ) -> int:
        """标记会话所有消息为已压缩。"""
        stmt = (
            select(SessionMessageModel)
            .where(SessionMessageModel.session_id == session_id)
        )
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        for msg in messages:
            msg.compacted = True
        await session.flush()
        return len(messages)

    async def mark_messages_compacted(
        self, session: AsyncSession, message_ids: list[str]
    ) -> int:
        """Mark selected messages as compacted."""
        if not message_ids:
            return 0
        stmt = select(SessionMessageModel).where(SessionMessageModel.message_id.in_(message_ids))
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        for msg in messages:
            msg.compacted = True
        await session.flush()
        return len(messages)


# 全局数据库服务实例
session_db = SessionDBService()
session_message_db = SessionMessageDBService()
