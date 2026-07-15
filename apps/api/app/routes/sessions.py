"""Agent Session API（数据库版本）。

使用 SQLAlchemy 异步数据库服务替代内存 store。
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.session import SessionModel, SessionMessageModel
from app.schemas.session import (
    MessageAppendRequest,
    MessageResponse,
    SessionCompactRequest,
    SessionCreateRequest,
    SessionResponse,
)
from app.services.db.session_db import session_db, session_message_db
from app.services.db.agent_db import agent_db
from app.services.db.identity_db import membership_db
from app.domain.identity import new_id

router = APIRouter()


@router.post("", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """创建 Agent Session。"""
    agent = await _get_agent_or_404(session, request.agent_id)
    await _assert_session_org_access(session, request.actor_user_id, agent.org_id)

    try:
        s = await session_db.create_session(
            session,
            session_id=new_id("ses"),
            org_id=agent.org_id,
            agent_id=agent.agent_id,
            user_id=request.actor_user_id,
            queue_mode=request.queue_mode,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_session_response(s)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    agent_id: str = Query(description="Agent ID"),
    actor_user_id: str = Query(description="操作者用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[SessionResponse]:
    """列出 Agent 下的 Session。"""
    agent = await _get_agent_or_404(session, agent_id)
    await _assert_session_org_access(session, actor_user_id, agent.org_id)
    sessions, _ = await session_db.list_agent_sessions(session, agent_id)

    return [_to_session_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
    db_session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """读取 Agent Session。"""
    s = await _get_session_or_404(db_session, session_id)
    await _assert_session_org_access(db_session, actor_user_id, s.org_id)

    return _to_session_response(s)


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def append_message(
    session_id: str,
    request: MessageAppendRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """向 Session 追加消息。"""
    s = await _get_session_or_404(session, session_id)
    await _assert_session_org_access(session, request.actor_user_id, s.org_id)

    try:
        if s.status == "closed":
            raise ValueError("会话已关闭")

        estimated_tokens = max(1, len(request.content) // 4)
        message = await session_message_db.append_message(
            session,
            message_id=new_id("msg"),
            session_id=s.session_id,
            org_id=s.org_id,
            agent_id=s.agent_id,
            role=request.role,
            content=request.content,
            estimated_tokens=estimated_tokens,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_message_response(message)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[MessageResponse]:
    """列出 Session 消息。"""
    s = await _get_session_or_404(session, session_id)
    await _assert_session_org_access(session, actor_user_id, s.org_id)
    messages = await session_message_db.list_session_messages(session, session_id)

    return [_to_message_response(m) for m in messages]


@router.post("/{session_id}/compact", response_model=SessionResponse)
async def compact_session(
    session_id: str,
    request: SessionCompactRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    """写入 Session 压缩摘要。"""
    s = await _get_session_or_404(db_session, session_id)
    await _assert_session_org_access(db_session, request.actor_user_id, s.org_id)

    try:
        s = await session_db.compact_session(db_session, s.session_id, request.summary)
        await session_message_db.mark_compacted(db_session, session_id)
        await db_session.commit()
    except ValueError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_session_response(s)


async def _get_agent_or_404(session: AsyncSession, agent_id: str):
    """Resolve an Agent without treating absence as an authorization failure."""

    try:
        return await agent_db.get_agent_required(session, agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _get_session_or_404(session: AsyncSession, session_id: str) -> SessionModel:
    """Resolve a Session without treating absence as an authorization failure."""

    try:
        return await session_db.get_session_required(session, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _assert_session_org_access(
    session: AsyncSession, actor_user_id: str, org_id: str
) -> None:
    """Reject an existing foreign-organization session without exposing it."""

    try:
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc


def _to_session_response(s: SessionModel) -> SessionResponse:
    """把 Session ORM 模型转换为 API 响应。"""
    return SessionResponse(
        session_id=s.session_id,
        org_id=s.org_id,
        agent_id=s.agent_id,
        user_id=s.user_id,
        queue_mode=s.queue_mode,
        status=s.status,
        compact_summary=s.compact_summary or "",
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _to_message_response(m: SessionMessageModel) -> MessageResponse:
    """把消息 ORM 模型转换为 API 响应。"""
    return MessageResponse(
        message_id=m.message_id,
        session_id=m.session_id,
        org_id=m.org_id,
        agent_id=m.agent_id,
        role=m.role,
        content=m.content,
        sequence=m.sequence,
        estimated_tokens=m.estimated_tokens,
        compacted=m.compacted,
        meta_info=_parse_message_meta_info(getattr(m, "meta_info", "{}")),
    )


def _parse_message_meta_info(raw_meta_info: object) -> dict[str, Any]:
    """Parse persisted message metadata, defaulting safely for legacy rows."""
    if isinstance(raw_meta_info, dict):
        return raw_meta_info
    if not raw_meta_info:
        return {}
    try:
        parsed = json.loads(str(raw_meta_info))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
