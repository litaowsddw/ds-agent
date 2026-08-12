"""Context Engine API（数据库版本）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.services.db.agent_db import agent_db, workspace_db
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import memory_db, skill_db
from app.services.db.session_db import session_db, session_message_db
from app.core.auth import AuthenticatedUser
from packages.runtime.context_engine import ContextEngine

router = APIRouter()


@router.get("/sessions/{session_id}/assemble")
async def assemble_session_context(
    session_id: str,
    auth: AuthenticatedUser,
    current_input: str = Query(default="", description="当前回合输入"),
    token_budget: int = Query(default=4096, description="上下文 token 预算"),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """从 Session 组装上下文。"""

    try:
        session = await session_db.get_session_required(db_session, session_id)
        await membership_db.assert_org_access(
            db_session, user_id=auth.user_id, org_id=session.org_id
        )
        workspace = await workspace_db.get_by_agent_id_required(db_session, session.agent_id)
        messages = await session_message_db.list_session_messages(db_session, session_id)
        skill_summaries = await skill_db.list_agent_allowed_skills(
            db_session, agent_id=session.agent_id, org_id=session.org_id
        )
        memories, _ = await memory_db.list_agent_memories(db_session, session.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    workspace_files = {
        "AGENTS.md": workspace.agents_md,
        "SOUL.md": workspace.soul_md,
        "TOOLS.md": workspace.tools_md,
        "MEMORY.md": workspace.memory_md,
    }
    message_dicts = [
        {
            "sequence": message.sequence,
            "role": message.role,
            "content": message.content,
        }
        for message in messages
    ]
    memory_dicts = [
        {
            "memory_type": memory.memory_type,
            "summary": memory.summary,
            "confidence": memory.confidence,
        }
        for memory in _rank_memory_summaries(memories, current_input)[:5]
    ]
    skill_dicts = [
        {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "scope": skill.scope,
        }
        for skill in skill_summaries
    ]

    engine = ContextEngine()
    return engine.assemble_from_session(
        workspace_files=workspace_files,
        compact_summary=session.compact_summary,
        messages=message_dicts,
        current_input=current_input,
        token_budget=token_budget,
        skill_summaries=skill_dicts,
        memories=memory_dicts,
    )


def _rank_memory_summaries(memories, query: str):
    """按当前输入粗排记忆摘要。"""

    terms = {term for term in query.lower().split() if term}
    if not terms:
        return list(memories)
    scored = []
    for memory in memories:
        haystack = f"{memory.summary}\n{memory.content}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score > 0:
            scored.append((score, memory))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [memory for _, memory in scored]
