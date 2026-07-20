"""Workflow execution application service."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.domain.identity import new_id
from app.gateway.llm import LLMGateway, OpenAICompatibleProvider, llm_gateway
from app.models.runtime import AgentMCPPolicyModel, MCPServerModel, MCPToolModel
from app.models.workflow import WorkflowRunModel
from app.routes.knowledge import search_knowledge_base
from app.schemas.knowledge import SearchRequest
from app.services.context_tokens import preflight_chat_context
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import model_provider_db
from app.services.db.workflow_db import (
    knowledge_base_db,
    node_run_db,
    workflow_db,
    workflow_run_db,
    workflow_version_db,
)
from app.services.metering import SessionUsageRecorder
from app.services.stream_usage import StreamUsageReporter
from packages.workflow.executor import ExecutedNode, WorkflowExecutor


UsageEventCallback = Callable[[dict[str, object]], Awaitable[None]]


class WorkflowExecutionService:
    """Create and execute workflow runs with persisted node-level trace."""

    async def create_and_execute(
        self,
        session: AsyncSession,
        *,
        version_id: str,
        input_data: dict[str, Any],
        actor_user_id: str,
        on_usage_event: UsageEventCallback | None = None,
    ) -> WorkflowRunModel:
        version = await workflow_version_db.get_by_id_required(session, version_id, "version_id")
        workflow = await workflow_db.get_workflow_required(session, version.workflow_id)
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=workflow.org_id)
        run = await workflow_run_db.create_run(
            session,
            run_id=new_id("run"),
            workflow_id=workflow.workflow_id,
            version_id=version.version_id,
            org_id=workflow.org_id,
            agent_id=workflow.agent_id,
            created_by=actor_user_id,
            input_data=input_data,
        )
        await session.flush()
        return await self.execute_existing_run(
            session,
            run=run,
            definition=json.loads(version.definition),
            input_data=input_data,
            actor_user_id=actor_user_id,
            on_usage_event=on_usage_event,
        )

    async def execute_existing_run(
        self,
        session: AsyncSession,
        *,
        run: WorkflowRunModel,
        definition: dict[str, Any],
        input_data: dict[str, Any],
        actor_user_id: str,
        on_usage_event: UsageEventCallback | None = None,
    ) -> WorkflowRunModel:
        await workflow_run_db.update_run_status(session, run.run_id, "running")
        execution_definition = definition
        if on_usage_event is not None:
            execution_definition = {
                **definition,
                "nodes": [
                    {
                        **node,
                        "config": {
                            **dict(node.get("config", {})),
                            "id": str(node["id"]),
                        },
                    }
                    if str(node.get("type")) == "llm"
                    else dict(node)
                    for node in definition.get("nodes", [])
                ],
            }
        executor = WorkflowExecutor(
            llm_gateway=lambda config, node_input: self._execute_llm_node(
                session=session,
                config=config,
                node_input=node_input,
                actor_user_id=actor_user_id,
                org_id=run.org_id,
                run=run,
                on_usage_event=on_usage_event,
            ),
            rag_search=lambda config, node_input: self._execute_rag_node(
                session=session,
                config=config,
                node_input=node_input,
                actor_user_id=actor_user_id,
                org_id=run.org_id,
            ),
            tool_call=lambda config, node_input: self._execute_tool_node(
                session=session,
                config=config,
                node_input=node_input,
                actor_user_id=actor_user_id,
                org_id=run.org_id,
                agent_id=run.agent_id,
            ),
        )
        result = await executor.execute_async(definition=execution_definition, input_data=input_data)
        for index, executed_node in enumerate(result.node_runs):
            await self._persist_executed_node(session, run.run_id, executed_node, index)
        await workflow_run_db.update_run_status(
            session,
            run.run_id,
            result.status,
            output_data=result.output_data,
            error_message=result.error_message,
        )
        await session.flush()
        return await workflow_run_db.get_run_required(session, run.run_id)

    async def _execute_llm_node(
        self,
        session: AsyncSession,
        config: dict[str, Any],
        node_input: dict[str, Any],
        actor_user_id: str,
        org_id: str,
        run: WorkflowRunModel,
        on_usage_event: UsageEventCallback | None = None,
    ) -> dict[str, Any]:
        provider_key = str(config.get("provider") or "")
        if not provider_key:
            raise ValueError("LLM 节点必须选择真实模型供应商")
        provider_config = await model_provider_db.get_by_key(session, org_id, provider_key)
        if provider_config is None or not provider_config.is_enabled:
            raise ValueError(f"模型供应商未配置或已禁用：{provider_key}")
        gateway = LLMGateway(
            providers={
                provider_key: OpenAICompatibleProvider(
                    base_url=provider_config.base_url,
                    api_key=decrypt_api_key(provider_config.api_key_encrypted),
                    provider_key=provider_key,
                )
            },
            limiter=llm_gateway.limiter,
            usage_recorder=SessionUsageRecorder(session),
        )
        enriched_config = {
            **config,
            "_org_id": org_id,
            "_actor_user_id": actor_user_id,
            "_agent_id": run.agent_id,
            "_workflow_id": run.workflow_id,
            "_workflow_version_id": run.version_id,
            "_workflow_run_id": run.run_id,
            "_workflow_node_id": str(config.get("id") or ""),
        }
        try:
            if on_usage_event is None:
                return await gateway.generate_from_workflow_node(enriched_config, node_input)
            request, _compiled = gateway.build_workflow_request(enriched_config, node_input)
            reporter = StreamUsageReporter(
                provider=request.provider,
                model=request.model,
                preflight=preflight_chat_context(
                    provider=request.provider,
                    model=request.model,
                    compiled_prompt=request.prompt,
                    components=[],
                ),
                usage_scope="workflow",
                usage_key=f"{run.run_id}:{config['id']}",
                workflow_node_id=str(config["id"]),
                token_limit=2400,
            )
            await on_usage_event(reporter.preflight_event())
            result = await gateway.stream_generate_from_workflow_node(
                enriched_config,
                node_input,
                on_text=lambda text: on_usage_event(reporter.append_text(text)),
            )
            usage = gateway.last_normalized_usage
            await on_usage_event(
                reporter.final_event(usage)
                if usage is not None
                else reporter.unavailable_final_event()
            )
            return result
        finally:
            llm_gateway.call_logs.extend(gateway.list_logs())

    async def _execute_rag_node(
        self,
        session: AsyncSession,
        config: dict[str, Any],
        node_input: dict[str, Any],
        actor_user_id: str,
        org_id: str,
    ) -> dict[str, Any]:
        kb_id = str(config.get("kb_id") or "")
        if not kb_id:
            raise ValueError("RAG 节点必须选择知识库")
        kb = await knowledge_base_db.get_by_id_required(session, kb_id, "kb_id")
        if kb.org_id != org_id:
            raise ValueError("RAG 节点不能访问其他组织的知识库")
        # WorkflowExecutor resolves every config template before callbacks are
        # invoked.  Do not render here again: user input can legitimately
        # contain literal ``{{...}}`` text and must not be treated as a second
        # template pass.
        query = str(config.get("query_template") or "").strip()
        if not query:
            query = _stringify_for_query(node_input.get("workflow_input", {}))
        limit = int(config.get("limit") or 5)
        chunks = await search_knowledge_base(
            kb_id=kb_id,
            request=SearchRequest(actor_user_id=actor_user_id, query=query, limit=limit),
            session=session,
        )
        return {
            "kb_id": kb_id,
            "query": query,
            "chunks": [chunk.model_dump() for chunk in chunks],
            "token_estimate": sum(chunk.estimated_tokens for chunk in chunks),
            "upstream": node_input.get("upstream", {}),
        }

    async def _execute_tool_node(
        self,
        session: AsyncSession,
        config: dict[str, Any],
        node_input: dict[str, Any],
        actor_user_id: str,
        org_id: str,
        agent_id: str,
    ) -> dict[str, Any]:
        tool_id = str(config.get("tool_id") or "")
        if not tool_id:
            raise ValueError("Tool 节点必须选择已授权工具")
        arguments = config.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=org_id)
        stmt = (
            select(MCPToolModel, MCPServerModel)
            .join(MCPServerModel, MCPToolModel.server_id == MCPServerModel.server_id)
            .join(AgentMCPPolicyModel, AgentMCPPolicyModel.server_id == MCPServerModel.server_id)
            .where(
                AgentMCPPolicyModel.agent_id == agent_id,
                AgentMCPPolicyModel.allowed == True,
                MCPToolModel.tool_id == tool_id,
                MCPServerModel.org_id == org_id,
            )
        )
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            raise ValueError("Agent 未授权调用该 MCP Tool")
        tool, server = row
        risk_level = str(config.get("risk_level") or tool.risk_level or "low")
        requires_approval = risk_level in {"high", "critical"}
        return {
            "tool_id": tool.tool_id,
            "tool_name": tool.name,
            "server_id": tool.server_id,
            "server_url": server.url,
            "risk_level": risk_level,
            "arguments": arguments,
            "status": "requires_approval" if requires_approval else "planned",
            "requires_approval": requires_approval,
            "upstream": node_input.get("upstream", {}),
        }

    async def _persist_executed_node(
        self,
        session: AsyncSession,
        run_id: str,
        executed_node: ExecutedNode,
        sequence: int,
    ) -> None:
        node_run = await node_run_db.create_node_run(
            session,
            node_run_id=f"{new_id('nr')}_{sequence:04d}",
            run_id=run_id,
            node_id=executed_node.node_id,
            node_type=executed_node.node_type,
            input_data=executed_node.input_data,
        )
        await node_run_db.update_node_run(
            session,
            node_run.node_run_id,
            status=executed_node.status,
            output_data=executed_node.output_data,
            error_message=executed_node.error_message,
            elapsed_ms=executed_node.elapsed_ms,
        )


def _stringify_for_query(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


workflow_execution_service = WorkflowExecutionService()
