"""Chat API routes."""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from starlette.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.core.security import decrypt_api_key
from app.database import get_db_session
from app.domain.identity import new_id
from app.services.chat_events import ChatTraceEvent, format_sse_event
from app.services.metering import SessionUsageRecorder, UsageContext
from app.services.skill_creator import (
    detect_skill_creation_request,
    extract_skill_markdown,
    write_skill_file,
)
from app.services.stream_usage import StreamUsageReporter

if TYPE_CHECKING:
    from apps.api.app.gateway.llm import LLMCallRequest, LLMGateway

logger = logging.getLogger(__name__)

router = APIRouter()


@dataclass(frozen=True, slots=True)
class StreamCallUpdate:
    """One client-visible update produced while one LLM call is streamed."""

    kind: Literal["preflight", "chunk", "final"]
    payload: dict[str, object]
    text: str = ""


async def _iterate_call_with_usage(
    gateway: "LLMGateway",
    request: "LLMCallRequest",
    reporter: StreamUsageReporter,
) -> AsyncIterator[StreamCallUpdate]:
    """Stream text with local progress followed by terminal provider usage."""

    yield StreamCallUpdate("preflight", reporter.preflight_event())
    stream = gateway.stream_generate(request)
    try:
        async for chunk in stream:
            yield StreamCallUpdate("chunk", reporter.append_text(chunk), text=chunk)
    finally:
        await stream.aclose()
    usage = gateway.last_normalized_usage
    payload = (
        reporter.final_event(usage) if usage is not None else reporter.unavailable_final_event()
    )
    yield StreamCallUpdate("final", payload)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    message: str
    session_id: str | None = None
    stream: bool = False
    async_exec: bool = False
    execution_mode: Literal["autonomous", "workflow"] = "autonomous"
    workflow_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    agent_id: str
    session_id: str
    mode: str
    intent: str = ""
    subtask_count: int = 0
    succeeded_count: int = 0
    plan_id: str = ""
    workflow_id: str = ""
    workflow_run_id: str = ""


async def _resolve_workflow_for_chat(db: AsyncSession, *, agent: Any, request: ChatRequest) -> Any:
    from apps.api.app.services.db.workflow_db import workflow_db

    workflow_id = request.workflow_id or agent.default_workflow_id or ""
    if not workflow_id:
        raise HTTPException(status_code=400, detail="请选择 Workflow 或改用自主模式")
    workflow = await workflow_db.get_workflow_required(db, workflow_id)
    if workflow.agent_id != request.agent_id:
        raise HTTPException(status_code=400, detail="Workflow 必须属于当前 Agent")
    if workflow.published_version_id is None:
        raise HTTPException(status_code=400, detail="Workflow 必须先发布")
    return workflow


def _workflow_message_metadata(workflow_id: str, workflow_run_id: str) -> dict[str, str]:
    return {
        "execution_mode": "workflow",
        "workflow_id": workflow_id,
        "workflow_run_id": workflow_run_id,
    }


def _require_server_authenticated_identity(auth: AuthenticatedUser) -> None:
    """Reject the development-only query-string actor fallback for chat usage."""

    if not auth.email:
        raise HTTPException(status_code=401, detail="Bearer token or service API key required")


async def _build_chat_llm_stack(
    db: AsyncSession,
    *,
    agent: Any,
    actor_user_id: str,
    source: str,
    session_id: str,
) -> tuple["LLMGateway", Any, Any]:
    """Delegate to the shared chat LLM stack builder (see services.chat_llm_stack)."""
    from app.services.chat_llm_stack import build_chat_llm_stack

    return await build_chat_llm_stack(
        db,
        agent=agent,
        actor_user_id=actor_user_id,
        source=source,
        session_id=session_id,
    )


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    auth: AuthenticatedUser,
    db: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    """Non-stream chat：单一流式编排管线的薄适配器。

    非流式执行全部走 `_chat_stream_events`（与 `/chat/stream` 完全同一条编排
    路径），本适配器只负责把事件流折叠回历史 JSON 契约。这样可以消灭
    双路径各自的会话/网关/执行逻辑漂移——任何 chat 行为差异只会出现在
    输出适配层，而不是在编排层。
    """
    final: dict[str, Any] = {}
    error_detail = ""
    error_status = 502

    async for block in _chat_stream_events(request=request, auth=auth, db=db):
        name, payload = _decode_sse_event(block)
        if name == "run_finished":
            final = payload
        elif name == "error":
            error_detail = str(payload.get("error") or "chat failed")
            error_status = int(payload.get("status_code") or 500)

    if error_detail:
        raise HTTPException(status_code=error_status, detail=error_detail)

    response_text = str(final.get("response") or "")
    session_id = str(final.get("session_id") or "")
    mode = str(final.get("mode") or "")
    if request.execution_mode == "workflow":
        mode = "workflow"
    elif not mode:
        from apps.api.app.services.db.agent_db import agent_db

        agent = await agent_db.get_agent_required(db, request.agent_id)
        mode = "supervisor" if str(agent.kind or "") == "SUPERVISOR" else "llm"

    return ChatResponse(
        response=response_text,
        agent_id=request.agent_id,
        session_id=session_id,
        mode=mode,
        workflow_id=str(final.get("workflow_id") or ""),
        workflow_run_id=str(final.get("workflow_run_id") or ""),
    )


def _decode_sse_event(block: str) -> tuple[str, dict[str, Any]]:
    """把一段 SSE 文本解析为 (event, payload)。"""
    name = ""
    payload: dict[str, Any] = {}
    for line in block.splitlines():
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            try:
                payload = json.loads(line[5:].strip())
            except ValueError:
                payload = {}
    return name, payload


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    auth: AuthenticatedUser,
    db: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    """Stream chat execution events and response chunks as SSE."""

    _require_server_authenticated_identity(auth)
    return StreamingResponse(
        _chat_stream_events(request=request, auth=auth, db=db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _chat_stream_events(
    request: ChatRequest,
    auth: AuthenticatedUser,
    db: AsyncSession,
) -> AsyncIterator[str]:
    from apps.api.app.gateway.llm import LLMCallRequest
    from apps.api.app.services.db.agent_db import agent_db
    from apps.api.app.services.db.identity_db import membership_db
    from apps.api.app.services.db.runtime_db import (
        agent_skill_policy_db,
        memory_db,
        skill_db,
        skill_evaluation_db,
    )
    from apps.api.app.services.db.session_db import session_db, session_message_db
    from apps.api.app.routes.skills import _parse_skill_markdown
    from apps.api.app.services.skill_disclosure import (
        build_skill_router_prompt,
        format_skill_description_catalog,
        load_selected_skill_context,
        parse_skill_selection,
    )
    from apps.api.app.services.hermes_memory import (
        build_compaction_prompt,
        build_memory_extraction_candidate,
        build_three_layer_memory_context,
        format_recent_messages,
    )
    from app.services.memory_vector import memory_vector_service

    run_id = new_id("chatrun")
    actor_user_id = auth.user_id

    async def emit(event: str, **data: object) -> str:
        return format_sse_event(ChatTraceEvent(event=event, data={"run_id": run_id, **data}))

    try:
        yield await emit("run_started", message=request.message)

        try:
            agent = await agent_db.get_agent_required(db, request.agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Agent not found") from exc
        org_id = str(agent.org_id)
        await membership_db.assert_org_access(db, user_id=actor_user_id, org_id=org_id)

        session_id = ""
        current_session = None
        if request.session_id:
            try:
                existing_session = await session_db.get_session_required(db, request.session_id)
                if existing_session.org_id != org_id or existing_session.agent_id != request.agent_id:
                    raise ValueError("Session does not belong to this agent")
                session_id = existing_session.session_id
                current_session = existing_session
            except ValueError:
                session_id = ""
        if not session_id:
            session = await session_db.create_session(
                db,
                session_id=new_id("ses"),
                org_id=org_id,
                agent_id=request.agent_id,
                user_id=actor_user_id,
            )
            session_id = session.session_id
            current_session = session

        current_user_message = await session_message_db.append_message(
            db,
            message_id=new_id("msg"),
            session_id=session_id,
            org_id=org_id,
            agent_id=request.agent_id,
            role="user",
            content=request.message,
            estimated_tokens=max(1, len(request.message) // 4),
        )

        if request.execution_mode == "workflow":
            from apps.api.app.routes.workflow_runs import stream_workflow_version_for_chat

            workflow = await _resolve_workflow_for_chat(db, agent=agent, request=request)

            yield await emit(
                "node_started",
                node="workflow",
                label="执行 Workflow",
                workflow_id=workflow.workflow_id,
                workflow_name=workflow.name,
            )
            async for update in stream_workflow_version_for_chat(
                db,
                version_id=workflow.published_version_id,
                input_data={"text": request.message},
                actor_user_id=actor_user_id,
                token_limit=_memory_compaction_threshold(agent.context_token_limit),
            ):
                if update.kind == "usage":
                    yield await emit(update.event_name, **update.payload)
                    continue

                run = update.run
                if run is None:
                    raise RuntimeError("Workflow chat stream completed without a run")
                response_text = json.dumps(
                    json.loads(run.output_data), ensure_ascii=False, sort_keys=True
                )
                await session_message_db.append_message(
                    db,
                    message_id=new_id("msg"),
                    session_id=session_id,
                    org_id=org_id,
                    agent_id=request.agent_id,
                    role="assistant",
                    content=response_text,
                    estimated_tokens=max(1, len(response_text) // 4),
                    meta_info=_workflow_message_metadata(workflow.workflow_id, run.run_id),
                )
                yield await emit(
                    "node_finished",
                    node="workflow",
                    label="执行 Workflow",
                    workflow_id=workflow.workflow_id,
                    workflow_run_id=run.run_id,
                )
                await db.commit()
                yield await emit(
                    "run_finished",
                    session_id=session_id,
                    response=response_text,
                    mode="workflow",
                    workflow_id=workflow.workflow_id,
                    workflow_run_id=run.run_id,
                )
                return

        model_provider = agent.model_provider or ""
        model_name = agent.model_name or ""
        gateway, adapter, chat_model = await _build_chat_llm_stack(
            db,
            agent=agent,
            actor_user_id=actor_user_id,
            source="chat_stream",
            session_id=str(session_id),
        )
        # Persist the current input before dispatch for resilience, but do not
        # feed it back as historical context.  It is appended exactly once as
        # the final native user message below.
        uncompacted_messages = await session_message_db.list_recent_uncompacted_messages(
            db, session_id, limit=200
        )
        recent_messages = [
            item
            for item in uncompacted_messages
            if item.message_id != current_user_message.message_id
        ]
        recalled_memories = await memory_vector_service.recall(
            db,
            org_id=org_id,
            agent_id=agent.agent_id,
            query=request.message,
            limit=5,
        )
        # The current session summary is deterministic session state, not a
        # retrieval result.  Older copies in the vector store must not replace
        # or duplicate it; vector recall remains a cross-session supplement.
        memories = [
            memory
            for memory in recalled_memories
            if not str(getattr(memory, "source", "")).startswith(
                f"session_compaction:{session_id}"
            )
        ]
        memory_context = build_three_layer_memory_context(
            recent_messages=recent_messages,
            compact_summary=(current_session.compact_summary if current_session else "") or "",
            memories=memories,
            token_threshold=_memory_compaction_threshold(agent.context_token_limit),
        )

        skill_intent = detect_skill_creation_request(request.message)
        allowed_skills = []
        skill_catalog = ""
        if not skill_intent.is_skill_request:
            from app.services.bundled_skills import list_bundled_skills

            allowed_skills = [
                *await skill_db.list_agent_allowed_skills(
                    db,
                    agent_id=agent.agent_id,
                    org_id=org_id,
                ),
                *list_bundled_skills(),
            ]
            skill_catalog = format_skill_description_catalog(allowed_skills)

        supervisors = await agent_db.list_org_agents(db, org_id, kind="SUPERVISOR")
        supervisor = sorted(supervisors, key=lambda item: item.created_at, reverse=True)[0] if supervisors else None
        planner = supervisor or agent

        yield await emit(
            "node_started",
            node="planning",
            label="开始规划",
            supervisor_id=planner.agent_id,
            supervisor_name=planner.name,
            supervisor_kind=planner.kind,
        )
        planned_action = "create_skill" if skill_intent.is_skill_request else "chat"
        yield await emit(
            "node_finished",
            node="planning",
            label="开始规划",
            action=planned_action,
            supervisor_id=planner.agent_id,
            supervisor_name=planner.name,
            fallback_to_agent=supervisor is None,
        )

        selected_skill_context = None
        actual_usage = None

        if skill_intent.is_skill_request:
            yield await emit(
                "node_started",
                node="skill_creator",
                label="使用 Skill Creator",
                agent_id=agent.agent_id,
                agent_name=agent.name,
                skill_topic=skill_intent.topic,
            )
            skill_prompt = _build_skill_prompt(skill_intent.topic)
            skill_system_prompt = (
                "You are a Skill Creator Agent. Output only a complete SKILL.md document."
            )
            skill_messages = [
                {"role": "system", "content": skill_system_prompt},
                {"role": "user", "content": skill_prompt},
            ]
            skill_compiled_prompt = f"[System]\n{skill_system_prompt}\n\n[User]\n{skill_prompt}"
            skill_components = [
                {
                    "key": "system",
                    "label": "System prompt",
                    "content": skill_system_prompt,
                    "stable_prefix": True,
                },
                {
                    "key": "current_user",
                    "label": "Current user message",
                    "content": skill_prompt,
                },
            ]
            from app.services.context_tokens import preflight_chat_context

            skill_preflight = preflight_chat_context(
                provider=model_provider,
                model=model_name,
                compiled_prompt=skill_compiled_prompt,
                components=skill_components,
                messages=skill_messages,
            )
            skill_reporter = StreamUsageReporter(
                provider=model_provider,
                model=model_name,
                preflight=skill_preflight,
                usage_scope="skill_create",
                usage_key=f"{run_id}:skill_creator",
                token_limit=_memory_compaction_threshold(agent.context_token_limit),
            )
            skill_request = LLMCallRequest(
                provider=model_provider,
                model=model_name,
                prompt=skill_compiled_prompt,
                messages=skill_messages,
                parameters={"temperature": 0.2, "max_tokens": 4096},
                metadata={
                    "source": "chat_skill_create",
                    "org_id": org_id,
                    "actor_user_id": actor_user_id,
                    "agent_id": agent.agent_id,
                    "session_id": session_id,
                },
            )
            raw_skill_parts: list[str] = []
            skill_final_payload: dict[str, object] | None = None
            try:
                async for update in _iterate_call_with_usage(
                    gateway, skill_request, skill_reporter
                ):
                    if update.kind == "preflight":
                        yield await emit("context_preflight", **update.payload)
                    elif update.kind == "chunk":
                        raw_skill_parts.append(update.text)
                        yield await emit("context_progress", **update.payload)
                    else:
                        skill_final_payload = update.payload
                actual_usage = gateway.last_normalized_usage
                skill_markdown = extract_skill_markdown("".join(raw_skill_parts))
                metadata = _parse_skill_markdown(skill_markdown)
                skill_root = Path(
                    os.getenv(
                        "AGENTFLOW_USER_SKILLS_DIR",
                        str(Path.home() / ".codex" / "skills" / "agentflow-user"),
                    )
                )
                skill_path = write_skill_file(skill_root, metadata["name"], skill_markdown)
                skill = await skill_db.create_skill(
                    db,
                    skill_id=new_id("skl"),
                    org_id=org_id,
                    team_id=agent.team_id,
                    agent_id=agent.agent_id,
                    scope="agent",
                    name=metadata["name"],
                    description=metadata["description"],
                    content=skill_markdown,
                    file_path=str(skill_path),
                    created_by=actor_user_id,
                )
                await agent_skill_policy_db.set_policy(
                    db,
                    agent_id=agent.agent_id,
                    skill_id=skill.skill_id,
                    allowed=True,
                )
            except Exception:
                if skill_final_payload is not None:
                    yield await emit("context_usage", **skill_reporter.unavailable_final_event())
                raise
            yield await emit(
                "context_usage",
                **(
                    skill_final_payload
                    if skill_final_payload is not None
                    else skill_reporter.unavailable_final_event()
                ),
            )
            response_text = f"已创建 Skill：{skill.name}\n路径：{skill_path}"
            yield await emit(
                "skill_created",
                node="skill_creator",
                skill_id=skill.skill_id,
                name=skill.name,
                path=str(skill_path),
            )
            yield await emit(
                "node_finished",
                node="skill_creator",
                label="使用 Skill Creator",
                skill_id=skill.skill_id,
                name=skill.name,
            )
        else:
            yield await emit(
                "node_started",
                node="skill_discovery",
                label="检索可用 Skill",
                agent_id=agent.agent_id,
                agent_name=agent.name,
            )
            skill_selection = None
            if skill_catalog:
                router_response = await adapter.call(
                    prompt=build_skill_router_prompt(request.message, skill_catalog),
                    system_prompt=(
                        "You are a skill router. You only decide whether a user request clearly "
                        "matches one available skill description. Return strict JSON only."
                    ),
                    temperature=0,
                    max_tokens=512,
                )
                skill_selection = parse_skill_selection(router_response, allowed_skills)
                if skill_selection is not None:
                    selected_skill_context = load_selected_skill_context(skill_selection, allowed_skills)
            yield await emit(
                "node_finished",
                node="skill_discovery",
                label="检索可用 Skill",
                available_count=len(allowed_skills),
                selected_count=1 if selected_skill_context is not None else 0,
                selected_skills=[selected_skill_context.name] if selected_skill_context is not None else [],
            )
            if selected_skill_context is not None:
                skill_label = f"使用 Skill：{selected_skill_context.name}"
                yield await emit(
                    "node_started",
                    node="skill_use",
                    label=skill_label,
                    skill_ids=[selected_skill_context.skill_id],
                    skill_names=[selected_skill_context.name],
                    loaded_resources=[path for path, _ in selected_skill_context.resources],
                )
                yield await emit(
                    "node_finished",
                    node="skill_use",
                    label=skill_label,
                    skill_ids=[selected_skill_context.skill_id],
                    skill_names=[selected_skill_context.name],
                    loaded_resources=[path for path, _ in selected_skill_context.resources],
                )
            yield await emit(
                "node_started",
                node="agent_call",
                label=f"调用 Agent：{agent.name}",
                agent_id=request.agent_id,
                agent_name=agent.name,
                model_provider=model_provider,
                model_name=model_name,
            )
            response_parts: list[str] = []
            compiled_prompt = _compile_agent_chat_prompt(
                agent,
                request.message,
                # Native compilation receives the three memory layers as
                # separate inputs below.  Do not pass the rendered legacy
                # block, otherwise an empty vector recall could duplicate the
                # summary and recent history.
                memory_context="",
                skill_catalog=skill_catalog,
                skill_context=(
                    selected_skill_context.prompt_context
                    if selected_skill_context is not None
                    else ""
                ),
                recent_messages=recent_messages,
                compact_summary=memory_context.compact_summary,
                long_term_context=memory_context.long_term_context,
            )
            from app.services.context_tokens import preflight_chat_context

            preflight = preflight_chat_context(
                provider=model_provider,
                model=model_name,
                compiled_prompt=str(compiled_prompt["compiled_prompt"]),
                components=compiled_prompt["context_breakdown"],
                messages=compiled_prompt["messages"],
            )
            llm_request = LLMCallRequest(
                provider=model_provider,
                model=model_name,
                prompt=str(compiled_prompt["compiled_prompt"]),
                messages=compiled_prompt["messages"],
                parameters={
                    "temperature": agent.temperature if agent.temperature is not None else 0.3,
                    "max_tokens": agent.max_tokens or _default_chat_max_tokens(),
                },
                metadata={
                    "source": "chat_stream",
                    "org_id": org_id,
                    "actor_user_id": actor_user_id,
                    "agent_id": agent.agent_id,
                    "session_id": session_id,
                },
                prefix_hash=str(compiled_prompt["prefix_hash"]),
            )
            reporter = StreamUsageReporter(
                provider=model_provider,
                model=model_name,
                preflight=preflight,
                usage_scope="chat",
                usage_key=f"{run_id}:agent_call",
                token_limit=_memory_compaction_threshold(agent.context_token_limit),
            )
            async for update in _iterate_call_with_usage(gateway, llm_request, reporter):
                if update.kind == "preflight":
                    yield await emit("context_preflight", **update.payload)
                elif update.kind == "chunk":
                    response_parts.append(update.text)
                    yield await emit("token", text=update.text, session_id=session_id)
                    yield await emit("context_progress", **update.payload)
                else:
                    actual_usage = gateway.last_normalized_usage
                    yield await emit("context_usage", **update.payload)
            response_text = "".join(response_parts)
            yield await emit(
                "node_finished",
                node="agent_call",
                label=f"调用 Agent：{agent.name}",
                agent_id=agent.agent_id,
                agent_name=agent.name,
            )

        yield await emit("node_started", node="final_answer", label="汇总结果")
        yield await emit("node_finished", node="final_answer", label="汇总结果")

        if response_text:
            memory_candidate = build_memory_extraction_candidate(request.message)
            if memory_candidate is not None:
                memory_type, memory_content = memory_candidate
                memory = await memory_db.create_memory(
                    db,
                    memory_id=new_id("mem"),
                    org_id=org_id,
                    agent_id=request.agent_id,
                    memory_type=memory_type,
                    content=memory_content,
                    summary=memory_content[:240],
                    confidence=0.85,
                    source="auto_hermes",
                )
                try:
                    memory_vector_service.upsert(memory)
                except Exception:
                    # A transient vector outage must not discard a successful
                    # user-visible answer or the durable SQL memory record.
                    pass
            if (
                selected_skill_context is not None
                # 内置技能不落库，skill_evaluations.skill_id 有指向 skills 表的外键，
                # 用 bdl_* ID 写库会违反外键约束；这类"平台标配"使用不需要评估跟踪。
                and not str(selected_skill_context.skill_id).startswith("bdl_")
            ):
                await skill_evaluation_db.create_evaluation(
                    db,
                    evaluation_id=new_id("seval"),
                    org_id=org_id,
                    agent_id=request.agent_id,
                    skill_id=selected_skill_context.skill_id,
                    session_id=session_id,
                    user_input=request.message,
                    assistant_output=response_text,
                    created_by=actor_user_id,
                )
            await session_message_db.append_message(
                db,
                message_id=new_id("msg"),
                session_id=session_id,
                org_id=org_id,
                agent_id=request.agent_id,
                role="assistant",
                content=response_text,
                estimated_tokens=max(1, len(response_text) // 4),
            )
            actual_context_tokens = actual_usage.input_tokens if actual_usage else None
            should_compact = (
                actual_context_tokens >= _memory_compaction_threshold(agent.context_token_limit)
                if actual_context_tokens is not None
                else memory_context.should_compact
            )
            if should_compact:
                # Keep a recent raw tail after compaction.  Only the old head
                # is folded into the durable session summary, matching the
                # OpenCode/Claude Code/Codex compaction model.
                all_uncompacted_messages = await session_message_db.list_recent_uncompacted_messages(
                    db, session_id, limit=200
                )
                preserve_recent_messages = 8
                messages_for_compaction = all_uncompacted_messages[:-preserve_recent_messages]
                if messages_for_compaction:
                    compacted_summary = await adapter.call(
                        prompt=build_compaction_prompt(
                            existing_summary=(current_session.compact_summary if current_session else "") or "",
                            messages_text=format_recent_messages(messages_for_compaction),
                        ),
                        system_prompt="You are a memory compaction agent. Output only the compressed memory summary.",
                        temperature=0,
                        max_tokens=768,
                    )
                    compacted_summary = compacted_summary.strip()
                    if compacted_summary:
                        summary_memory = await memory_db.create_memory(
                            db,
                            memory_id=new_id("mem"),
                            org_id=org_id,
                            agent_id=request.agent_id,
                            memory_type="session_summary",
                            content=compacted_summary,
                            summary=compacted_summary[:240],
                            confidence=0.9,
                            source=f"session_compaction:{session_id}",
                        )
                        try:
                            memory_vector_service.upsert(summary_memory)
                        except Exception:
                            pass
                    # The summary stays in the session and is sent on every
                    # following turn.  The vector copy is for cross-session
                    # recall only; it is never the sole continuity mechanism.
                    await session_db.compact_session(db, session_id, compacted_summary)
                    await session_message_db.mark_messages_compacted(
                        db,
                        [message.message_id for message in messages_for_compaction],
                    )
        await db.commit()
        yield await emit("run_finished", session_id=session_id, response=response_text)
    except asyncio.CancelledError:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        status_code = exc.status_code if isinstance(exc, HTTPException) else 500
        yield await emit("error", error=str(detail), status_code=status_code)


def _build_agent_prompt(
    agent: object,
    message: str,
    *,
    memory_context: str = "",
    skill_catalog: str = "",
    skill_context: str = "",
) -> str:
    agent_name = str(getattr(agent, "name", "") or "Agent")
    agent_description = str(getattr(agent, "description", "") or "").strip()
    agent_instructions = str(getattr(agent, "system_prompt", "") or "").strip()
    from packages.runtime.system_prompt import build_agent_system_prompt

    system_prompt = build_agent_system_prompt(
        agent_name=agent_name,
        agent_description=agent_description,
        agent_instructions=agent_instructions,
    )
    if memory_context.strip():
        system_prompt = f"{system_prompt}\n\n{memory_context.strip()}"
    if skill_catalog.strip():
        system_prompt = (
            f"{system_prompt}\n\n[Available Skill Descriptions]\n"
            "Only these skill descriptions are visible at the discovery layer. "
            "Use the loaded SKILL.md instructions only if a skill context is provided below.\n"
            f"{skill_catalog.strip()}"
        )
    if skill_context.strip():
        system_prompt = f"{system_prompt}\n\n[Loaded Skill]\n{skill_context.strip()}"
    return f"[System]\n{system_prompt}\n\n[User]\n{message}"


def _compile_agent_chat_prompt(
    agent: object,
    message: str,
    *,
    memory_context: str = "",
    skill_catalog: str = "",
    skill_context: str = "",
    recent_messages: list[object] | None = None,
    compact_summary: str = "",
    long_term_context: str = "",
) -> dict[str, object]:
    """Compile a cache-friendly native message sequence for one chat turn.

    The session summary is deterministic continuity state and replaces only
    compacted history.  Recalled long-term memory is deliberately placed near
    the active request so a retrieval change never rewrites prior turns.
    """
    from packages.runtime.prompt_compiler import PromptContextCompiler
    from packages.runtime.system_prompt import build_agent_system_prompt

    agent_name = str(getattr(agent, "name", "") or "Agent")
    agent_description = str(getattr(agent, "description", "") or "").strip()
    agent_instructions = str(getattr(agent, "system_prompt", "") or "").strip()
    system_prompt = build_agent_system_prompt(
        agent_name=agent_name,
        agent_description=agent_description,
        agent_instructions=agent_instructions,
    )
    immutable_prefix = [
        {"role": "system", "content": system_prompt},
        {
            "role": "system",
            "content": "[Runtime capability boundary]\n"
            "Relevant memories, skills, and retrieved knowledge are provided as context. "
            "Only tools supplied through structured schemas are executable; "
            "MCP tools outside that schema remain unavailable.",
        },
    ]
    if skill_catalog.strip():
        immutable_prefix.append(
            {
                "role": "system",
                "content": "[Available Skill Descriptions]\n"
                "Only these descriptions are visible at discovery time.\n"
                + skill_catalog.strip(),
            }
        )

    # ``memory_context`` is retained as a compatibility input for callers that
    # have not yet split session continuity from retrieved memory.  The chat
    # route supplies ``long_term_context`` explicitly, so it never duplicates
    # the compact summary or recent tail.
    effective_long_term_context = long_term_context or memory_context

    compiled = PromptContextCompiler().compile_messages(
        immutable_prefix=immutable_prefix,
        session_summary=compact_summary,
        recent_messages=[
            {"role": str(getattr(item, "role", "user") or "user"), "content": str(getattr(item, "content", "") or "")}
            for item in (recent_messages or [])
        ],
        long_term_context=effective_long_term_context,
        loaded_skill=skill_context,
        current_turn=message,
    )
    compiled["context_breakdown"] = _prompt_structure_breakdown(
        immutable_prefix=immutable_prefix,
        skill_catalog=skill_catalog,
        skill_context=skill_context,
        recent_messages=recent_messages or [],
        compact_summary=compact_summary,
        long_term_context=effective_long_term_context,
        current_message=message,
    )
    return compiled


def _prompt_structure_breakdown(
    *,
    immutable_prefix: list[dict[str, str]],
    skill_catalog: str,
    skill_context: str,
    recent_messages: list[object],
    compact_summary: str,
    long_term_context: str,
    current_message: str,
) -> list[dict[str, object]]:
    """Describe native message components in exactly the order sent upstream."""

    def section(key: str, label: str, content: str, *, stable_prefix: bool = False) -> dict[str, object]:
        return {
            "key": key,
            "label": label,
            "content": content,
            "bytes": len(content.encode("utf-8")),
            "stable_prefix": stable_prefix,
        }

    sections = [
        section("system", "System prompt", immutable_prefix[0]["content"], stable_prefix=True),
        section("agent", "Agent configuration", immutable_prefix[1]["content"], stable_prefix=True),
    ]
    if skill_catalog.strip():
        sections.append(section("tools", "Tools / Skills catalog", immutable_prefix[-1]["content"], stable_prefix=True))
    if compact_summary.strip():
        sections.append(
            section(
                "memory_summary",
                "Compressed session summary",
                "[Session compaction summary]\n" + compact_summary.strip(),
            )
        )
    for item in sorted(recent_messages, key=lambda value: int(getattr(value, "sequence", 0))):
        role = str(getattr(item, "role", "") or "")
        key = "user_history" if role == "user" else "assistant_history" if role == "assistant" else "other_history"
        label = "User history" if role == "user" else "Assistant history" if role == "assistant" else "Other history"
        sections.append(section(key, label, str(getattr(item, "content", "") or "")))
    if long_term_context.strip():
        sections.append(
            section(
                "long_term_memory",
                "Relevant long-term memory",
                "[Relevant long-term memory; use only when applicable]\n" + long_term_context.strip(),
            )
        )
    if skill_context.strip():
        sections.append(
            section(
                "loaded_skill",
                "Loaded skill instructions",
                "[Loaded skill instructions]\n" + skill_context.strip(),
            )
        )
    sections.append(section("current_user", "Current user message", current_message))
    return sections


def _default_chat_max_tokens() -> int:
    raw_value = os.getenv("AGENTFLOW_CHAT_MAX_TOKENS", "1024")
    try:
        return max(128, int(raw_value))
    except ValueError:
        return 1024


def _memory_compaction_threshold(configured_limit: int | None = None) -> int:
    if configured_limit is not None:
        return max(800, configured_limit)
    raw_value = os.getenv("AGENTFLOW_MEMORY_COMPACTION_TOKENS", "2400")
    try:
        return max(800, int(raw_value))
    except ValueError:
        return 2400


def _build_skill_prompt(topic: str) -> str:
    return f"""Create a production-ready SKILL.md for this user request:
{topic}

Requirements:
- Output only Markdown.
- Include YAML frontmatter with name and description.
- Use a short lowercase hyphenated name.
- Include concrete trigger guidance, step-by-step workflow, examples, and limits.
- The skill should be useful for an Agent platform user.
"""


def _chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return [""]
    return [text[index : index + size] for index in range(0, len(text), size)]


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    auth: AuthenticatedUser,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Return persisted messages for a chat session."""

    try:
        from apps.api.app.services.db.identity_db import membership_db
        from apps.api.app.services.db.session_db import session_db, session_message_db

        # 会话消息是租户数据：读取前必须校验成员身份
        session = await session_db.get_session_required(db, session_id)
        try:
            await membership_db.assert_org_access(db, user_id=auth.user_id, org_id=session.org_id)
        except ValueError:
            raise HTTPException(status_code=403, detail="Forbidden")

        messages = await session_message_db.list_session_messages(db, session_id, limit=limit)
        return {
            "session_id": session_id,
            "messages": [_to_chat_message_response(message) for message in messages] if messages else [],
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load chat messages: {exc}") from exc


@router.get("/agents/{agent_id}/latest-session")
async def get_latest_agent_session(
    agent_id: str,
    auth: AuthenticatedUser,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Return the newest persisted chat session for an Agent."""

    try:
        from app.models.session import SessionModel
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.services.db.identity_db import membership_db
        from apps.api.app.services.db.session_db import session_message_db

        agent = await agent_db.get_agent_required(db, agent_id)
        await membership_db.assert_org_access(db, user_id=auth.user_id, org_id=agent.org_id)

        result = await db.execute(
            select(SessionModel)
            .where(SessionModel.agent_id == agent_id)
            .order_by(desc(SessionModel.created_at))
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return {"session_id": None, "messages": []}

        messages = await session_message_db.list_session_messages(db, session.session_id)
        return {
            "session_id": session.session_id,
            "messages": [_to_chat_message_response(message) for message in messages],
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load latest chat session: {exc}") from exc


def _parse_message_meta_info(raw_meta_info: object) -> dict[str, Any]:
    if isinstance(raw_meta_info, dict):
        return raw_meta_info
    if not raw_meta_info:
        return {}
    try:
        parsed = json.loads(str(raw_meta_info))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_chat_message_response(message: object) -> dict[str, object]:
    return {
        "message_id": str(getattr(message, "message_id", "")),
        "role": getattr(message, "role", ""),
        "content": getattr(message, "content", ""),
        "sequence": getattr(message, "sequence", 0),
        "meta_info": _parse_message_meta_info(getattr(message, "meta_info", "{}")),
        "created_at": str(message.created_at) if getattr(message, "created_at", None) else "",
    }
