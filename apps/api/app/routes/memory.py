"""Memory API。"""

from fastapi import APIRouter, HTTPException

from apps.api.app.domain.memory import Memory
from apps.api.app.schemas.memory import MemoryCreateRequest, MemoryRecallRequest, MemoryResponse
from apps.api.app.services.memory_store import memory_store

router = APIRouter()


@router.post("", response_model=MemoryResponse)
async def create_memory(request: MemoryCreateRequest) -> MemoryResponse:
    """写入 Agent 长期记忆。"""

    try:
        memory = memory_store.create_memory(
            actor_user_id=request.actor_user_id,
            agent_id=request.agent_id,
            memory_type=request.memory_type,
            content=request.content,
            summary=request.summary,
            confidence=request.confidence,
            source=request.source,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_memory_response(memory)


@router.post("/recall", response_model=list[MemoryResponse])
async def recall_memories(request: MemoryRecallRequest) -> list[MemoryResponse]:
    """召回 Agent 长期记忆。"""

    try:
        memories = memory_store.recall_memories(
            actor_user_id=request.actor_user_id,
            agent_id=request.agent_id,
            query=request.query,
            limit=request.limit,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_memory_response(memory) for memory in memories]


def _to_memory_response(memory: Memory) -> MemoryResponse:
    """把 Memory 领域模型转换为 API 响应。"""

    return MemoryResponse(
        memory_id=memory.memory_id,
        org_id=memory.org_id,
        agent_id=memory.agent_id,
        user_id=memory.user_id,
        memory_type=memory.memory_type,
        content=memory.content,
        summary=memory.summary,
        confidence=memory.confidence,
        source=memory.source,
    )

