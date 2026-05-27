"""Context Engine API。

本路由把 Agent Workspace、Session 历史和 ContextEngine 连接起来，
用于前端 Context Inspector 和后续 LLM Gateway 调用前的上下文组装。
"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.services.agent_store import agent_store
from apps.api.app.services.memory_store import memory_store
from apps.api.app.services.session_store import session_store
from apps.api.app.services.skill_store import skill_store
from packages.runtime.context_engine import ContextEngine

router = APIRouter()


@router.get("/sessions/{session_id}/assemble")
async def assemble_session_context(
    session_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
    current_input: str = Query(default="", description="当前回合输入"),
    token_budget: int = Query(default=4096, description="上下文 token 预算"),
) -> dict[str, object]:
    """从 Session 组装上下文。"""

    try:
        session = session_store.get_session(actor_user_id=actor_user_id, session_id=session_id)
        workspace = agent_store.get_workspace(
            actor_user_id=actor_user_id,
            agent_id=session.agent_id,
        )
        messages = session_store.list_messages(actor_user_id=actor_user_id, session_id=session_id)
        skill_summaries = skill_store.list_allowed_skill_summaries(
            actor_user_id=actor_user_id,
            agent_id=session.agent_id,
        )
        memories = memory_store.recall_memories(
            actor_user_id=actor_user_id,
            agent_id=session.agent_id,
            query=current_input,
            limit=5,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # workspace_files 是字符串 key 的 Workspace 文件，方便 ContextEngine 稳定排序。
    workspace_files = {file_kind.value: content for file_kind, content in workspace.files.items()}

    # message_dicts 是传给 Runtime 包的轻量消息结构，避免 Runtime 依赖 API 领域模型。
    message_dicts = [
        {
            "sequence": message.sequence,
            "role": message.role.value,
            "content": message.content,
        }
        for message in messages
    ]

    # memory_dicts 是传给 Runtime 包的轻量记忆结构。
    memory_dicts = [
        {
            "memory_type": memory.memory_type.value,
            "summary": memory.summary,
            "confidence": memory.confidence,
        }
        for memory in memories
    ]

    engine = ContextEngine()
    return engine.assemble_from_session(
        workspace_files=workspace_files,
        compact_summary=session.compact_summary,
        messages=message_dicts,
        current_input=current_input,
        token_budget=token_budget,
        skill_summaries=skill_summaries,
        memories=memory_dicts,
    )
