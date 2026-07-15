"""Memory API（数据库版本）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity import new_id
from app.models.runtime import MemoryModel
from app.schemas.memory import MemoryCreateRequest, MemoryRecallRequest, MemoryResponse
from app.services.db.agent_db import agent_db
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import memory_db
from app.services.memory_vector import memory_vector_service

router = APIRouter()


@router.post("", response_model=MemoryResponse)
async def create_memory(
    request: MemoryCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MemoryResponse:
    """写入 Agent 长期记忆。"""

    agent = await _get_agent_or_404(session, request.agent_id)
    await _assert_memory_org_access(session, request.actor_user_id, agent.org_id)

    try:
        memory = await memory_db.create_memory(
            session,
            memory_id=new_id("mem"),
            org_id=agent.org_id,
            agent_id=request.agent_id,
            memory_type=str(request.memory_type.value if hasattr(request.memory_type, "value") else request.memory_type),
            content=request.content,
            summary=request.summary or request.content[:200],
            confidence=request.confidence,
            source=request.source,
        )
        try:
            memory_vector_service.upsert(memory)
        except Exception:
            # The SQL record remains durable and will be available for retry or
            # lexical fallback if the configured vector backend is unavailable.
            pass
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_memory_response(memory, user_id=request.actor_user_id)


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    actor_user_id: str = Query(description="操作用户 ID"),
    agent_id: str = Query(description="Agent ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryResponse]:
    """列出 Agent 下的记忆。"""

    agent = await _get_agent_or_404(session, agent_id)
    await _assert_memory_org_access(session, actor_user_id, agent.org_id)
    memories, _ = await memory_db.list_agent_memories(session, agent_id)

    return [_to_memory_response(memory, user_id=actor_user_id) for memory in memories]


@router.post("/recall", response_model=list[MemoryResponse])
async def recall_memories(
    request: MemoryRecallRequest,
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryResponse]:
    """召回 Agent 长期记忆。"""

    agent = await _get_agent_or_404(session, request.agent_id)
    await _assert_memory_org_access(session, request.actor_user_id, agent.org_id)
    memories, _ = await memory_db.list_agent_memories(session, request.agent_id)

    ranked = _rank_memories(memories, request.query)
    return [
        _to_memory_response(memory, user_id=request.actor_user_id)
        for memory in ranked[: request.limit]
    ]


async def _get_agent_or_404(session: AsyncSession, agent_id: str):
    """Resolve the requested Agent without treating a missing record as an access denial."""

    try:
        return await agent_db.get_agent_required(session, agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _assert_memory_org_access(
    session: AsyncSession, actor_user_id: str, org_id: str
) -> None:
    """Reject an existing foreign-organization resource without exposing its data."""

    try:
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc


def _rank_memories(memories: list[MemoryModel], query: str) -> list[MemoryModel]:
    """用轻量关键词相关性排序记忆。"""

    terms = {term for term in query.lower().split() if term}
    if not terms:
        return list(memories)
    scored: list[tuple[int, MemoryModel]] = []
    for memory in memories:
        haystack = f"{memory.content}\n{memory.summary}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score > 0:
            scored.append((score, memory))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [memory for _, memory in scored]


def _to_memory_response(memory: MemoryModel, user_id: str) -> MemoryResponse:
    """把 Memory ORM 模型转换为 API 响应。"""

    return MemoryResponse(
        memory_id=memory.memory_id,
        org_id=memory.org_id,
        agent_id=memory.agent_id,
        user_id=user_id,
        memory_type=memory.memory_type,
        content=memory.content,
        summary=memory.summary,
        confidence=memory.confidence,
        source=memory.source,
    )
