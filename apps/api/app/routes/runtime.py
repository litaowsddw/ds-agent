"""Agent Runtime API（真实 Agent 版本）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.services.db.agent_db import agent_db
from app.services.db.identity_db import membership_db
from app.core.auth import AuthenticatedUser
from packages.runtime.agent_runtime import AgentRuntime
from packages.runtime.context_engine import ContextEngine
from packages.runtime.prompt_compiler import PromptContextCompiler
from packages.runtime.subagent import AgentKind

router = APIRouter()


@router.get("/describe")
async def describe_runtime(
    auth: AuthenticatedUser,
    agent_id: str = Query(description="Agent ID"),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """返回真实 Agent Runtime 能力描述。"""

    try:
        agent = await agent_db.get_agent_required(session, agent_id)
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=agent.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    runtime = AgentRuntime(
        agent_id=agent.agent_id,
        org_id=agent.org_id,
        kind=AgentKind(getattr(agent, "kind", "USER_SUB") or "USER_SUB"),
        model_provider=agent.model_provider or "",
        model_name=agent.model_name or "",
        workspace_id=agent.workspace_id or "",
    )
    return runtime.describe()


@router.post("/context/assemble")
async def assemble_context(payload: dict[str, object], auth: AuthenticatedUser) -> dict[str, object]:
    """组装一次调用方显式传入的上下文。"""

    token_budget = int(payload.get("token_budget", 4096))
    user_input = str(payload.get("user_input", ""))
    workspace_files = payload.get("workspace_files", {})
    messages = payload.get("messages", [])
    skill_summaries = payload.get("skill_summaries", [])
    memories = payload.get("memories", [])

    engine = ContextEngine()
    return engine.assemble_from_session(
        workspace_files=workspace_files if isinstance(workspace_files, dict) else {},
        compact_summary=str(payload.get("compact_summary", "")),
        messages=messages if isinstance(messages, list) else [],
        current_input=user_input,
        token_budget=token_budget,
        skill_summaries=skill_summaries if isinstance(skill_summaries, list) else [],
        memories=memories if isinstance(memories, list) else [],
    )


@router.post("/prompt/compile")
async def compile_prompt(payload: dict[str, object], auth: AuthenticatedUser) -> dict[str, object]:
    """编译 Reasonix 风格的 prefix-cache 友好 Prompt。"""

    compiler = PromptContextCompiler()
    return compiler.compile(
        immutable_prefix=payload.get("immutable_prefix", {}),
        append_only_log=payload.get("append_only_log", []),
        current_turn=payload.get("current_turn", {}),
    )
