"""Agent Session API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.session import AgentSession, SessionMessage
from apps.api.app.schemas.session import (
    MessageAppendRequest,
    MessageResponse,
    SessionCompactRequest,
    SessionCreateRequest,
    SessionResponse,
)
from apps.api.app.services.session_store import session_store

router = APIRouter()


@router.post("", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest) -> SessionResponse:
    """创建 Agent Session。"""

    try:
        session = session_store.create_session(
            actor_user_id=request.actor_user_id,
            agent_id=request.agent_id,
            queue_mode=request.queue_mode,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_session_response(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    agent_id: str = Query(description="Agent ID"),
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[SessionResponse]:
    """列出 Agent 下的 Session。"""

    try:
        sessions = session_store.list_sessions(actor_user_id=actor_user_id, agent_id=agent_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [_to_session_response(session) for session in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> SessionResponse:
    """读取 Agent Session。"""

    try:
        session = session_store.get_session(actor_user_id=actor_user_id, session_id=session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_session_response(session)


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def append_message(session_id: str, request: MessageAppendRequest) -> MessageResponse:
    """向 Session 追加消息。"""

    try:
        message = session_store.append_message(
            actor_user_id=request.actor_user_id,
            session_id=session_id,
            role=request.role,
            content=request.content,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_message_response(message)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[MessageResponse]:
    """列出 Session 消息。"""

    try:
        messages = session_store.list_messages(actor_user_id=actor_user_id, session_id=session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [_to_message_response(message) for message in messages]


@router.post("/{session_id}/compact", response_model=SessionResponse)
async def compact_session(session_id: str, request: SessionCompactRequest) -> SessionResponse:
    """写入 Session 压缩摘要。"""

    try:
        session = session_store.compact_session(
            actor_user_id=request.actor_user_id,
            session_id=session_id,
            summary=request.summary,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_session_response(session)


def _to_session_response(session: AgentSession) -> SessionResponse:
    """把 Session 领域模型转换为 API 响应。"""

    return SessionResponse(
        session_id=session.session_id,
        org_id=session.org_id,
        agent_id=session.agent_id,
        user_id=session.user_id,
        queue_mode=session.queue_mode,
        status=session.status,
        compact_summary=session.compact_summary,
    )


def _to_message_response(message: SessionMessage) -> MessageResponse:
    """把消息领域模型转换为 API 响应。"""

    return MessageResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        org_id=message.org_id,
        agent_id=message.agent_id,
        role=message.role,
        content=message.content,
        sequence=message.sequence,
        estimated_tokens=message.estimated_tokens,
        compacted=message.compacted,
    )

