"""Chat API routes."""

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Literal

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

router = APIRouter()


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


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    auth: AuthenticatedUser,
    db: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    """Chat with an Agent through its configured real model provider."""

    try:
        _require_server_authenticated_identity(auth)
        from apps.api.app.gateway.llm import LLMGateway, OpenAICompatibleProvider, llm_gateway
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.services.db.identity_db import membership_db
        from apps.api.app.services.db.runtime_db import model_provider_db
        from apps.api.app.services.db.session_db import session_db, session_message_db
        from packages.runtime.agent_runtime import AgentKind, AgentRuntime
        from packages.runtime.llm_caller import LLMCallerAdapter

        try:
            agent = await agent_db.get_agent_required(db, request.agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Agent not found") from exc

        org_id = str(agent.org_id)
        await membership_db.assert_org_access(db, user_id=auth.user_id, org_id=org_id)
        actor_user_id = auth.user_id

        session_id = ""
        if request.session_id:
            try:
                existing_session = await session_db.get_session_required(db, request.session_id)
                if existing_session.org_id != org_id or existing_session.agent_id != request.agent_id:
                    raise ValueError("Session does not belong to this agent")
                session_id = existing_session.session_id
            except ValueError:
                session_id = ""

        if not session_id:
            session = await session_db.create_session(
                db,
                session_id=new_id("ses"),
                org_id=org_id,
                agent_id=request.agent_id,
                user_id=agent.created_by,
            )
            session_id = str(session.session_id)

        await session_message_db.append_message(
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
            from apps.api.app.routes.workflow_runs import execute_workflow_version_for_chat

            workflow = await _resolve_workflow_for_chat(db, agent=agent, request=request)

            run = await execute_workflow_version_for_chat(
                db,
                version_id=workflow.published_version_id,
                input_data={"text": request.message},
                actor_user_id=actor_user_id,
            )
            response_text = json.dumps(json.loads(run.output_data), ensure_ascii=False, sort_keys=True)
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
            await db.commit()
            return ChatResponse(
                response=response_text,
                agent_id=request.agent_id,
                session_id=session_id,
                mode="workflow",
                workflow_id=workflow.workflow_id,
                workflow_run_id=run.run_id,
            )

        model_provider = agent.model_provider or ""
        model_name = agent.model_name or ""
        if not model_provider or not model_name:
            raise HTTPException(status_code=400, detail="Agent has no model provider or model configured")

        provider_config = await model_provider_db.get_by_key(db, org_id, model_provider)
        if provider_config is None or not provider_config.is_enabled:
            raise HTTPException(status_code=400, detail=f"Model provider not configured: {model_provider}")

        gateway = LLMGateway(
            providers={
                model_provider: OpenAICompatibleProvider(
                    base_url=provider_config.base_url,
                    api_key=(
                        decrypt_api_key(provider_config.api_key_encrypted)
                        if provider_config.api_key_encrypted
                        else ""
                    ),
                    provider_key=model_provider,
                )
            },
            limiter=llm_gateway.limiter,
            usage_recorder=SessionUsageRecorder(db),
        )
        adapter = LLMCallerAdapter(
            gateway=gateway,
            provider=model_provider,
            model=model_name,
            org_id=org_id,
            actor_user_id=actor_user_id,
            metadata=UsageContext(
                org_id=org_id,
                actor_user_id=actor_user_id,
                source="chat_autonomous",
                api_name="chat.completions",
                agent_id=str(agent.agent_id),
                session_id=str(session_id),
            ).as_metadata(),
        )

        runtime = AgentRuntime(
            agent_id=request.agent_id,
            org_id=org_id,
            model_provider=model_provider,
            model_name=model_name,
            workspace_id=agent.workspace_id or "",
            llm_caller=adapter,
        )

        agent_kind_str = agent.kind or "USER_SUB"
        if agent_kind_str == AgentKind.SUPERVISOR.value or agent_kind_str == "SUPERVISOR":
            runtime.init_supervisor(llm_caller=adapter)

        if request.async_exec:
            raise HTTPException(
                status_code=501,
                detail="Async supervisor execution is disabled until metered attribution is available.",
            )
            from apps.worker.app.tasks.subagent import supervisor_run_cycle

            supervisor_run_cycle.delay(
                supervisor_agent_id=request.agent_id,
                org_id=org_id,
                user_input=request.message,
            )
            await db.commit()
            return ChatResponse(
                response="Task submitted and running asynchronously.",
                agent_id=request.agent_id,
                session_id=session_id,
                mode="async",
            )

        result = await runtime.chat(request.message, session_id=session_id)
        if result.get("error"):
            raise HTTPException(status_code=502, detail=str(result["error"]))

        response_text = str(result.get("response") or "")
        if response_text:
            try:
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
            except Exception:
                pass

        await db.commit()
        return ChatResponse(
            response=response_text,
            agent_id=request.agent_id,
            session_id=session_id,
            mode=str(result.get("mode") or ("supervisor" if agent_kind_str == "SUPERVISOR" else "direct")),
            intent=str(result.get("intent") or ""),
            subtask_count=int(result.get("subtask_count") or 0),
            succeeded_count=int(result.get("succeeded_count") or 0),
            plan_id=str(result.get("plan_id") or ""),
        )

    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc


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
    from apps.api.app.gateway.llm import LLMCallRequest, LLMGateway, OpenAICompatibleProvider, llm_gateway
    from apps.api.app.services.db.agent_db import agent_db
    from apps.api.app.services.db.identity_db import membership_db
    from apps.api.app.services.db.runtime_db import (
        agent_skill_policy_db,
        memory_db,
        model_provider_db,
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
    from packages.runtime.llm_caller import LLMCallerAdapter

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

        await session_message_db.append_message(
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
            from apps.api.app.routes.workflow_runs import execute_workflow_version_for_chat

            workflow = await _resolve_workflow_for_chat(db, agent=agent, request=request)

            yield await emit(
                "node_started",
                node="workflow",
                label="执行 Workflow",
                workflow_id=workflow.workflow_id,
                workflow_name=workflow.name,
            )
            run = await execute_workflow_version_for_chat(
                db,
                version_id=workflow.published_version_id,
                input_data={"text": request.message},
                actor_user_id=actor_user_id,
            )
            response_text = json.dumps(json.loads(run.output_data), ensure_ascii=False, sort_keys=True)
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
            for chunk in _chunk_text(response_text):
                yield await emit("token", text=chunk, session_id=session_id)
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
        if not model_provider or not model_name:
            raise HTTPException(status_code=400, detail="Agent has no model provider or model configured")

        provider_config = await model_provider_db.get_by_key(db, org_id, model_provider)
        if provider_config is None or not provider_config.is_enabled:
            raise HTTPException(status_code=400, detail=f"Model provider not configured: {model_provider}")
        gateway = LLMGateway(
            providers={
                model_provider: OpenAICompatibleProvider(
                    base_url=provider_config.base_url,
                    api_key=(
                        decrypt_api_key(provider_config.api_key_encrypted)
                        if provider_config.api_key_encrypted
                        else ""
                    ),
                    provider_key=model_provider,
                )
            },
            limiter=llm_gateway.limiter,
            usage_recorder=SessionUsageRecorder(db),
        )
        adapter = LLMCallerAdapter(
            gateway=gateway,
            provider=model_provider,
            model=model_name,
            org_id=org_id,
            actor_user_id=actor_user_id,
            metadata=UsageContext(
                org_id=org_id,
                actor_user_id=actor_user_id,
                source="chat_stream",
                api_name="chat.completions",
                agent_id=str(agent.agent_id),
                session_id=str(session_id),
            ).as_metadata(),
        )
        recent_messages = await session_message_db.list_recent_uncompacted_messages(db, session_id, limit=24)
        memories, _ = await memory_db.list_agent_memories(db, agent.agent_id, limit=20)
        memory_context = build_three_layer_memory_context(
            recent_messages=recent_messages,
            compact_summary=(current_session.compact_summary if current_session else "") or "",
            memories=memories,
            token_threshold=_memory_compaction_threshold(agent.context_token_limit),
        )

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
        skill_intent = detect_skill_creation_request(request.message)
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
            raw_skill = await adapter.call(
                prompt=skill_prompt,
                system_prompt="You are a Skill Creator Agent. Output only a complete SKILL.md document.",
                temperature=0.2,
                max_tokens=4096,
            )
            skill_markdown = extract_skill_markdown(raw_skill)
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
            allowed_skills = await skill_db.list_agent_allowed_skills(
                db,
                agent_id=agent.agent_id,
                org_id=org_id,
            )
            skill_catalog = format_skill_description_catalog(allowed_skills)
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
                memory_context=memory_context.prompt_context,
                skill_catalog=skill_catalog,
                skill_context=(
                    selected_skill_context.prompt_context
                    if selected_skill_context is not None
                    else ""
                ),
            )
            llm_request = LLMCallRequest(
                provider=model_provider,
                model=model_name,
                prompt=str(compiled_prompt["compiled_prompt"]),
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
            llm_stream = gateway.stream_generate(llm_request)
            try:
                async for chunk in llm_stream:
                    response_parts.append(chunk)
                    yield await emit("token", text=chunk, session_id=session_id)
            finally:
                await llm_stream.aclose()
            actual_usage = gateway.last_normalized_usage
            yield await emit(
                "context_usage",
                input_tokens=(actual_usage.input_tokens if actual_usage else None),
                cache_read_input_tokens=(
                    actual_usage.cache_read_input_tokens if actual_usage else None
                ),
                usage_status=(actual_usage.usage_status if actual_usage else "unavailable"),
                token_limit=_memory_compaction_threshold(agent.context_token_limit),
            )
            response_text = "".join(response_parts)
            yield await emit(
                "node_finished",
                node="agent_call",
                label=f"调用 Agent：{agent.name}",
                agent_id=agent.agent_id,
                agent_name=agent.name,
            )

        yield await emit("node_started", node="final_answer", label="汇总结果")
        if skill_intent.is_skill_request:
            for chunk in _chunk_text(response_text):
                yield await emit("token", text=chunk, session_id=session_id)
        yield await emit("node_finished", node="final_answer", label="汇总结果")

        if response_text:
            memory_candidate = build_memory_extraction_candidate(request.message)
            if memory_candidate is not None:
                memory_type, memory_content = memory_candidate
                await memory_db.create_memory(
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
            if selected_skill_context is not None:
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
                messages_for_compaction = recent_messages[-18:]
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
                    await session_db.compact_session(db, session_id, compacted_summary.strip())
                    await session_message_db.mark_messages_compacted(
                        db,
                        [message.message_id for message in messages_for_compaction],
                    )
        await db.commit()
        yield await emit("run_finished", session_id=session_id, response=response_text)
    except Exception as exc:
        await db.rollback()
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        yield await emit("error", error=str(detail))


def _build_agent_prompt(
    agent: object,
    message: str,
    *,
    memory_context: str = "",
    skill_catalog: str = "",
    skill_context: str = "",
) -> str:
    system_prompt = str(getattr(agent, "system_prompt", "") or "").strip()
    agent_name = str(getattr(agent, "name", "") or "Agent")
    agent_description = str(getattr(agent, "description", "") or "").strip()
    if not system_prompt:
        system_prompt = f"You are {agent_name}. Answer the user directly and accurately."
    if agent_description:
        system_prompt = f"{system_prompt}\n\nAgent description: {agent_description}"
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
) -> dict[str, object]:
    """Compile chat input so its leading bytes stay stable across turns.

    Only Agent configuration and the discoverable skill catalog form the immutable
    prefix. Conversation/memory and the selected Skill stay outside it, preventing
    an individual turn from invalidating the structural prefix eligibility metric.
    """
    from packages.runtime.prompt_compiler import PromptContextCompiler

    agent_name = str(getattr(agent, "name", "") or "Agent")
    system_prompt = str(getattr(agent, "system_prompt", "") or "").strip()
    if not system_prompt:
        system_prompt = f"You are {agent_name}. Answer the user directly and accurately."

    immutable_prefix = {
        "agent": {
            "name": agent_name,
            "description": str(getattr(agent, "description", "") or "").strip(),
            "system_prompt": system_prompt,
        },
        "skill_catalog": skill_catalog.strip(),
        "response_contract": "Answer the user directly and accurately.",
    }
    return PromptContextCompiler().compile(
        immutable_prefix=immutable_prefix,
        append_only_log={
            "memory_context": memory_context.strip(),
            "loaded_skill": skill_context.strip(),
        },
        current_turn={"message": message},
    )


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
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Return persisted messages for a chat session."""

    try:
        from apps.api.app.services.db.session_db import session_message_db

        messages = await session_message_db.list_session_messages(db, session_id, limit=limit)
        return {
            "session_id": session_id,
            "messages": [_to_chat_message_response(message) for message in messages] if messages else [],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load chat messages: {exc}") from exc


@router.get("/agents/{agent_id}/latest-session")
async def get_latest_agent_session(
    agent_id: str,
    actor_user_id: str = Query(description="Actor user ID"),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Return the newest persisted chat session for an Agent."""

    try:
        from app.models.session import SessionModel
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.services.db.identity_db import membership_db
        from apps.api.app.services.db.session_db import session_message_db

        agent = await agent_db.get_agent_required(db, agent_id)
        await membership_db.assert_org_access(db, user_id=actor_user_id, org_id=agent.org_id)

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
