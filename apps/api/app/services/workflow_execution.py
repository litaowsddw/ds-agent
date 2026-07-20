"""Workflow execution application service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any

from jsonschema import FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key, encrypt_api_key
from app.domain.identity import new_id
from app.gateway.llm import LLMGateway, OpenAICompatibleProvider, llm_gateway
from app.models.runtime import AgentMCPPolicyModel, MCPServerModel, MCPToolModel
from app.models.workflow import WorkflowApprovalRequestModel, WorkflowRunModel
from app.routes.knowledge import search_knowledge_base
from app.schemas.knowledge import SearchRequest
from app.services.context_tokens import preflight_chat_context
from app.services.db.identity_db import audit_log_db, membership_db
from app.services.db.runtime_db import model_provider_db
from app.services.db.workflow_db import (
    knowledge_base_db,
    node_run_db,
    workflow_approval_db,
    workflow_db,
    workflow_run_db,
    workflow_version_db,
)
from app.services.metering import SessionUsageRecorder
from app.services.stream_usage import StreamUsageReporter
from app.services.external_import import ExternalImportError, invoke_streamable_http_tool
from packages.workflow.executor import (
    ExecutedNode,
    WorkflowApprovalRequired,
    WorkflowExecutor,
)


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
                config={**config, "_workflow_run_id": run.run_id},
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
        # Risk comes exclusively from the imported Tool snapshot.  A workflow
        # author must never lower policy by placing a different ``risk_level``
        # in canvas JSON.
        risk_level = str(tool.risk_level or "").strip().lower()
        run_id = str(config.get("_workflow_run_id") or "")
        node_id = str(config.get("id") or "")
        try:
            _validate_mcp_tool_arguments(tool.input_schema, arguments)
        except ValueError as exc:
            await self._append_tool_audit(
                session=session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                run_id=run_id,
                node_id=node_id,
                tool=tool,
                status="rejected",
                arguments=arguments,
                detail={"reason": "MCP Tool input schema validation failed", "error": str(exc)},
            )
            raise
        if risk_level != "low":
            if not run_id or not node_id:
                raise ValueError("High-risk MCP Tool may only run as a persisted Workflow node")
            approval = await workflow_approval_db.create_pending(
                session,
                approval_id=new_id("wfa"),
                run_id=run_id,
                org_id=org_id,
                node_id=node_id,
                tool_id=tool.tool_id,
                server_id=server.server_id,
                tool_name=tool.name,
                risk_level=risk_level or "unknown",
                arguments_redacted=_audit_safe_payload(arguments),
                arguments_encrypted=encrypt_api_key(json.dumps(arguments, ensure_ascii=False)),
                requested_by=actor_user_id,
            )
            await self._append_tool_audit(
                session=session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                run_id=run_id,
                node_id=node_id,
                tool=tool,
                status="approval_required",
                arguments=arguments,
                detail={
                    "approval_id": approval.approval_id,
                    "risk_level": risk_level or "unknown",
                    "reason": "该运行时没有可验证、持久化的人类审批记录",
                },
            )
            raise WorkflowApprovalRequired(
                approval.approval_id,
                f"MCP Tool '{tool.name}' requires human approval (需要人工审批) before its external action runs",
            )
            raise ValueError(
                f"MCP Tool '{tool.name}' 风险等级为 {risk_level or 'unknown'}，"
                "需要人工审批；当前 Workflow 运行时不会执行未审批的外部操作"
            )

        try:
            _validate_mcp_tool_arguments(tool.input_schema, arguments)
        except ValueError as exc:
            await self._append_tool_audit(
                session=session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                run_id=run_id,
                node_id=node_id,
                tool=tool,
                status="rejected",
                arguments=arguments,
                detail={"reason": "MCP Tool input_schema 校验失败", "error": str(exc)},
            )
            raise

        # Import is deliberately the only supported way to bind an external
        # executable connector.  Legacy manually registered HTTP/SSE servers
        # keep their metadata but cannot become an SSRF-capable action node.
        if str(server.transport) != "streamable_http":
            await self._append_tool_audit(
                session=session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                run_id=run_id,
                node_id=node_id,
                tool=tool,
                status="rejected",
                arguments=arguments,
                detail={
                    "reason": "仅已导入的 streamable_http MCP 支持运行时调用",
                    "transport": str(server.transport),
                },
            )
            raise ValueError("仅已导入的 streamable_http MCP Tool 可以在 Workflow 中执行")

        try:
            credential_headers = _load_mcp_credential_headers(server.credentials_encrypted)
        except ValueError as exc:
            await self._append_tool_audit(
                session=session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                run_id=run_id,
                node_id=node_id,
                tool=tool,
                status="rejected",
                arguments=arguments,
                detail={"reason": "MCP 凭据配置无效", "error": str(exc)},
            )
            raise

        # Record the intent before the remote side effect.  No credentials are
        # placed in this log, and all user-controlled payloads are redacted and
        # bounded.  The resolved input/output also remains in the node trace.
        await self._append_tool_audit(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            run_id=run_id,
            node_id=node_id,
            tool=tool,
            status="started",
            arguments=arguments,
            detail={"risk_level": "low", "server_id": server.server_id},
        )
        try:
            mcp_result = await asyncio.to_thread(
                invoke_streamable_http_tool,
                server.url,
                credential_headers,
                tool_name=tool.name,
                arguments=arguments,
            )
        except ExternalImportError as exc:
            await self._append_tool_audit(
                session=session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                run_id=run_id,
                node_id=node_id,
                tool=tool,
                status="failed",
                arguments=arguments,
                detail={"error": str(exc)},
            )
            raise ValueError(f"MCP Tool '{tool.name}' 调用失败：{exc}") from exc
        except Exception as exc:
            # Keep the original exception out of the public response and audit
            # to avoid leaking transport implementation details or secrets.
            await self._append_tool_audit(
                session=session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                run_id=run_id,
                node_id=node_id,
                tool=tool,
                status="failed",
                arguments=arguments,
                detail={"error": "MCP Tool 运行时发生未预期错误"},
            )
            raise ValueError(f"MCP Tool '{tool.name}' 调用失败：运行时错误") from exc

        result = {
            "tool_id": tool.tool_id,
            "tool_name": tool.name,
            "server_id": tool.server_id,
            "risk_level": "low",
            "arguments": arguments,
            "status": "succeeded",
            "requires_approval": False,
            "result": mcp_result,
            "upstream": node_input.get("upstream", {}),
        }
        await self._append_tool_audit(
            session=session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            run_id=run_id,
            node_id=node_id,
            tool=tool,
            status="succeeded",
            arguments=arguments,
            detail={"result": mcp_result},
        )
        return result

    async def decide_high_risk_tool_approval(
        self,
        session: AsyncSession,
        *,
        run: WorkflowRunModel,
        approval_id: str,
        decision: str,
        actor_user_id: str,
    ) -> WorkflowApprovalRequestModel:
        """Make one durable approval decision and, on approval, execute one Tool step.

        The generic DAG executor has no durable LangGraph checkpoint.  Replaying
        the complete graph after approval could repeat successful external
        actions, so this method only creates a new execution record for the
        paused Tool node.  It intentionally leaves the run in
        ``awaiting_manual_resume`` rather than falsely claiming the entire DAG
        completed.
        """

        if decision not in {"approve", "reject"}:
            raise ValueError("Unsupported approval decision")
        approval = await workflow_approval_db.get_run_approval_required(
            session,
            run_id=run.run_id,
            approval_id=approval_id,
            for_update=True,
        )
        if approval.status != "pending":
            raise ValueError("This approval request has already been decided or claimed")

        if decision == "reject":
            approval.status = "rejected"
            approval.decided_by = actor_user_id
            approval.decided_at = _utcnow()
            await workflow_run_db.update_run_status(
                session,
                run.run_id,
                "canceled",
                output_data={"approval_id": approval.approval_id, "decision": "rejected"},
                error_message="High-risk MCP Tool was rejected by an authorized operator",
            )
            await self._append_approval_audit(
                session=session,
                approval=approval,
                actor_user_id=actor_user_id,
                action="rejected",
                detail={},
            )
            await session.flush()
            return approval

        # Persist the one-time execution claim before the remote side effect.
        # A duplicate request seeing ``executing`` is rejected instead of
        # risking a second side effect.  A process crash therefore requires
        # explicit operational reconciliation, never an automatic replay.
        approval.status = "executing"
        approval.decided_by = actor_user_id
        approval.decided_at = _utcnow()
        await self._append_approval_audit(
            session=session,
            approval=approval,
            actor_user_id=actor_user_id,
            action="execution_claimed",
            detail={},
        )
        await session.commit()

        try:
            tool, server = await self._get_current_authorized_tool(
                session=session,
                run=run,
                approval=approval,
            )
            arguments = _decrypt_approval_arguments(approval.arguments_encrypted)
            _validate_mcp_tool_arguments(tool.input_schema, arguments)
            if str(server.transport) != "streamable_http":
                raise ValueError("Approved MCP Tool is no longer a controlled streamable HTTP import")
            credential_headers = _load_mcp_credential_headers(server.credentials_encrypted)
            await self._append_approval_audit(
                session=session,
                approval=approval,
                actor_user_id=actor_user_id,
                action="execution_started",
                detail={"server_id": server.server_id},
            )
            # Make the intent visible and durable before contacting the remote
            # server, which is vital when later transport status is uncertain.
            await session.commit()
            mcp_result = await asyncio.to_thread(
                invoke_streamable_http_tool,
                server.url,
                credential_headers,
                tool_name=tool.name,
                arguments=arguments,
            )
        except Exception as exc:
            # Do not make an automatic retry available after any ambiguous
            # transport error: a remote system might have completed the action.
            approval.status = "execution_failed"
            approval.error_message = "Approved MCP Tool did not produce a confirmed result; reconcile it before retrying."
            await self._append_approval_audit(
                session=session,
                approval=approval,
                actor_user_id=actor_user_id,
                action="execution_failed",
                detail={"error": _safe_approval_error(exc)},
            )
            await session.commit()
            return approval

        existing_node_runs = await node_run_db.list_run_node_runs(session, run.run_id)
        node_run = await node_run_db.create_node_run(
            session,
            node_run_id=f"{new_id('nr')}_{len(existing_node_runs):04d}",
            run_id=run.run_id,
            node_id=approval.node_id,
            node_type="tool",
            input_data={
                "approval_id": approval.approval_id,
                "arguments": json.loads(approval.arguments_redacted),
                "execution_mode": "approved_retry_step",
            },
        )
        safe_result = _audit_safe_payload(mcp_result)
        await node_run_db.update_node_run(
            session,
            node_run.node_run_id,
            status="succeeded",
            output_data={
                "approval_id": approval.approval_id,
                "tool_id": tool.tool_id,
                "tool_name": tool.name,
                "arguments": json.loads(approval.arguments_redacted),
                "result": safe_result,
                "execution_mode": "approved_retry_step",
            },
        )
        approval.status = "approved"
        approval.execution_node_run_id = node_run.node_run_id
        approval.error_message = ""
        await workflow_run_db.update_run_status(
            session,
            run.run_id,
            "awaiting_manual_resume",
            output_data={
                "approval_id": approval.approval_id,
                "approved_node_run_id": node_run.node_run_id,
                "status": "approved_step_completed",
            },
        )
        await self._append_approval_audit(
            session=session,
            approval=approval,
            actor_user_id=actor_user_id,
            action="approved_step_succeeded",
            detail={"execution_node_run_id": node_run.node_run_id, "result": safe_result},
        )
        await session.commit()
        return approval

    async def _get_current_authorized_tool(
        self,
        *,
        session: AsyncSession,
        run: WorkflowRunModel,
        approval: WorkflowApprovalRequestModel,
    ) -> tuple[MCPToolModel, MCPServerModel]:
        """Recheck organization, Agent policy, and immutable Tool identity at decision time."""

        statement = (
            select(MCPToolModel, MCPServerModel)
            .join(MCPServerModel, MCPToolModel.server_id == MCPServerModel.server_id)
            .join(AgentMCPPolicyModel, AgentMCPPolicyModel.server_id == MCPServerModel.server_id)
            .where(
                AgentMCPPolicyModel.agent_id == run.agent_id,
                AgentMCPPolicyModel.allowed == True,
                MCPToolModel.tool_id == approval.tool_id,
                MCPServerModel.server_id == approval.server_id,
                MCPServerModel.org_id == run.org_id,
            )
        )
        result = await session.execute(statement)
        row = result.first()
        if row is None:
            raise ValueError("The Agent is no longer authorized to execute this MCP Tool")
        tool, server = row
        if tool.name != approval.tool_name or str(tool.risk_level or "").strip().lower() == "low":
            raise ValueError("The approved MCP Tool snapshot no longer matches current high-risk policy")
        return tool, server

    async def _append_approval_audit(
        self,
        *,
        session: AsyncSession,
        approval: WorkflowApprovalRequestModel,
        actor_user_id: str,
        action: str,
        detail: dict[str, Any],
    ) -> None:
        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=approval.org_id,
            actor_user_id=actor_user_id,
            action=f"workflow.approval.{action}",
            resource_type="workflow_approval",
            resource_id=approval.approval_id,
            detail={
                "workflow_run_id": approval.run_id,
                "workflow_node_id": approval.node_id,
                "tool_id": approval.tool_id,
                "tool_name": approval.tool_name,
                "risk_level": approval.risk_level,
                "arguments": json.loads(approval.arguments_redacted),
                **_audit_safe_payload(detail),
            },
        )

    async def _append_tool_audit(
        self,
        *,
        session: AsyncSession,
        org_id: str,
        actor_user_id: str,
        run_id: str,
        node_id: str,
        tool: MCPToolModel,
        status: str,
        arguments: dict[str, Any],
        detail: dict[str, Any],
    ) -> None:
        """Record a bounded, credential-safe MCP execution audit event."""

        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=f"workflow.mcp_tool.{status}",
            resource_type="mcp_tool",
            resource_id=tool.tool_id,
            detail={
                "workflow_run_id": run_id,
                "workflow_node_id": node_id,
                "server_id": tool.server_id,
                "tool_name": tool.name,
                "arguments": _audit_safe_payload(arguments),
                **_audit_safe_payload(detail),
            },
        )

    async def _persist_executed_node(
        self,
        session: AsyncSession,
        run_id: str,
        executed_node: ExecutedNode,
        sequence: int,
    ) -> None:
        output_data = dict(executed_node.output_data)
        # A successful second attempt is otherwise indistinguishable from a
        # first attempt in the persisted trace. Keep execution metadata under
        # a reserved key without changing the node's business output shape.
        if executed_node.attempt_count != 1 or executed_node.last_error:
            output_data["_execution"] = {
                "attempt_count": executed_node.attempt_count,
                "last_error": executed_node.last_error,
            }
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
            output_data=output_data,
            error_message=executed_node.error_message,
            elapsed_ms=executed_node.elapsed_ms,
        )


def _stringify_for_query(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _utcnow() -> datetime:
    """Keep approval decision timestamps server-owned and timezone-consistent."""

    return datetime.utcnow()


def _decrypt_approval_arguments(arguments_encrypted: str) -> dict[str, Any]:
    """Read the exact resolved arguments without exposing them to API clients."""

    try:
        decoded = json.loads(decrypt_api_key(arguments_encrypted))
    except Exception as exc:
        raise ValueError("The persisted approval parameters cannot be decrypted") from exc
    if not isinstance(decoded, dict):
        raise ValueError("The persisted approval parameters are invalid")
    return decoded


def _safe_approval_error(exc: Exception) -> str:
    """Avoid returning connector implementation details or credential-bearing errors."""

    if isinstance(exc, (ValueError, ExternalImportError)):
        return _audit_safe_payload(str(exc))
    return "Unexpected error while executing the approved MCP Tool"


def _load_mcp_credential_headers(credentials_encrypted: str | None) -> dict[str, str]:
    """Load credentials created by MCP import without exposing them in traces."""

    # Only the reviewed import flow writes an encrypted credentials envelope
    # (including encrypted ``{}`` for public MCPs).  Legacy registry records
    # have an empty value, so accepting them would let a manually registered
    # server bypass the import-time HTTPS/SSRF review boundary.
    if not credentials_encrypted:
        raise ValueError("MCP Server 未通过受控导入绑定，禁止在 Workflow 中执行")
    try:
        raw = decrypt_api_key(credentials_encrypted)
        decoded = json.loads(raw)
    except Exception as exc:
        raise ValueError("MCP 凭据无法解密或格式无效") from exc
    if not isinstance(decoded, Mapping):
        raise ValueError("MCP 凭据格式无效")
    headers: dict[str, str] = {}
    for name, value in decoded.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("MCP 凭据格式无效")
        headers[name] = value
    return headers


def _validate_mcp_tool_arguments(input_schema_raw: str | None, arguments: dict[str, Any]) -> None:
    """Validate resolved Tool arguments against the imported MCP JSON Schema.

    MCP schemas are integration-owned data.  Using the maintained JSON Schema
    implementation keeps Draft selection, nested objects, arrays, required
    fields, and format validation consistent instead of approximating a
    security boundary with a partial hand-written validator.
    """

    try:
        input_schema = json.loads(input_schema_raw or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("已导入 MCP Tool 的 input_schema 不是有效 JSON") from exc
    if not isinstance(input_schema, dict):
        raise ValueError("已导入 MCP Tool 的 input_schema 必须是 JSON 对象")
    _assert_local_json_schema_references(input_schema)
    try:
        validator_class = validator_for(input_schema)
        validator_class.check_schema(input_schema)
        validator = validator_class(input_schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(arguments), key=lambda error: list(error.absolute_path))
    except SchemaError as exc:
        raise ValueError("已导入 MCP Tool 的 input_schema 不合法") from exc
    if not errors:
        return
    first_error = errors[0]
    path = ".".join(str(part) for part in first_error.absolute_path) or "参数对象"
    raise ValueError(f"MCP Tool 参数未通过 input_schema 校验（{path}）：{first_error.message}")


def _assert_local_json_schema_references(value: Any) -> None:
    """Keep imported schemas data-only and prevent validator-time SSRF via `$ref`."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in {"$ref", "$dynamicRef"}:
                if not isinstance(nested, str) or not nested.startswith("#"):
                    raise ValueError("已导入 MCP Tool 的 input_schema 不允许外部 $ref")
            _assert_local_json_schema_references(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_local_json_schema_references(nested)


_AUDIT_SENSITIVE_FIELD_PARTS = (
    "access_key",
    "api_key",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "header",
    "password",
    "private_key",
    "secret",
    "token",
)
_MAX_AUDIT_VALUE_CHARS = 4_000
_MAX_AUDIT_COLLECTION_ITEMS = 50


def _audit_safe_payload(value: Any, *, _depth: int = 0) -> Any:
    """Preserve useful Tool evidence without putting secrets or huge data in audit logs."""

    if _depth >= 6:
        return "[truncated: nesting limit]"
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, nested) in enumerate(value.items()):
            if index >= _MAX_AUDIT_COLLECTION_ITEMS:
                result["_truncated"] = f"{len(value) - _MAX_AUDIT_COLLECTION_ITEMS} items omitted"
                break
            key_text = str(key)
            if any(part in key_text.lower() for part in _AUDIT_SENSITIVE_FIELD_PARTS):
                result[key_text] = "[redacted]"
            else:
                result[key_text] = _audit_safe_payload(nested, _depth=_depth + 1)
        return result
    if isinstance(value, list):
        items = [
            _audit_safe_payload(item, _depth=_depth + 1)
            for item in value[:_MAX_AUDIT_COLLECTION_ITEMS]
        ]
        if len(value) > _MAX_AUDIT_COLLECTION_ITEMS:
            items.append(f"[truncated: {len(value) - _MAX_AUDIT_COLLECTION_ITEMS} items omitted]")
        return items
    if isinstance(value, str):
        suffix = "[truncated]" if len(value) > _MAX_AUDIT_VALUE_CHARS else ""
        return value[:_MAX_AUDIT_VALUE_CHARS] + suffix
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_AUDIT_VALUE_CHARS]


workflow_execution_service = WorkflowExecutionService()
