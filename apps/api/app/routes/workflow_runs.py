"""Workflow Run API。

这个路由负责把已发布 Workflow 版本真正执行起来：
- LLM 节点调用组织配置的真实模型供应商；
- RAG 节点调用知识库向量/关键词检索；
- Tool 节点校验 MCP 授权并生成受控调用计划。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.database import get_db_session
from app.domain.identity import new_id
from app.gateway.llm import LLMGateway, OpenAICompatibleProvider, llm_gateway
from app.models.runtime import AgentMCPPolicyModel, MCPServerModel, MCPToolModel
from app.models.workflow import NodeRunModel, WorkflowRunModel
from app.schemas.knowledge import SearchRequest
from app.schemas.workflow_run import (
    NodeRunResponse,
    WorkflowRunCreateRequest,
    WorkflowRunResponse,
)
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import model_provider_db
from app.services.db.workflow_db import (
    knowledge_base_db,
    node_run_db,
    workflow_db,
    workflow_run_db,
    workflow_version_db,
)
from app.routes.knowledge import search_knowledge_base
from packages.workflow.executor import ExecutedNode, WorkflowExecutor

router = APIRouter()


@router.post("", response_model=WorkflowRunResponse)
async def create_run(
    request: WorkflowRunCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    """创建并执行 Workflow Run。"""

    try:
        version = await workflow_version_db.get_by_id_required(
            session, request.version_id, "version_id"
        )
        workflow = await workflow_db.get_workflow_required(session, version.workflow_id)
        await membership_db.assert_org_access(
            session, user_id=request.actor_user_id, org_id=workflow.org_id
        )

        run = await workflow_run_db.create_run(
            session,
            run_id=new_id("run"),
            workflow_id=workflow.workflow_id,
            version_id=version.version_id,
            org_id=workflow.org_id,
            agent_id=workflow.agent_id,
            created_by=request.actor_user_id,
            input_data=request.input_data,
        )
        await session.commit()

        definition = json.loads(version.definition)
        if request.async_mode:
            await _submit_async_run(run=run, definition=definition, request=request)
        else:
            await _execute_run_now(
                session=session,
                run=run,
                definition=definition,
                input_data=request.input_data,
                actor_user_id=request.actor_user_id,
            )
            await session.commit()
            run = await workflow_run_db.get_run_required(session, run.run_id)

    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_run_response(run)


async def execute_workflow_version_for_chat(
    session: AsyncSession,
    *,
    version_id: str,
    input_data: dict[str, Any],
    actor_user_id: str,
) -> WorkflowRunModel:
    """创建并同步执行 Workflow Run，供 Chat 流程模式复用。"""

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
    await _execute_run_now(
        session=session,
        run=run,
        definition=json.loads(version.definition),
        input_data=input_data,
        actor_user_id=actor_user_id,
    )
    await session.flush()
    return await workflow_run_db.get_run_required(session, run.run_id)


@router.get("", response_model=list[WorkflowRunResponse])
async def list_runs(
    actor_user_id: str = Query(description="操作用户 ID"),
    workflow_id: str | None = Query(default=None, description="Workflow ID"),
    org_id: str | None = Query(default=None, description="Organization ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowRunResponse]:
    """列出用户可访问的 Workflow Run。"""

    try:
        if workflow_id is not None:
            workflow = await workflow_db.get_workflow_required(session, workflow_id)
            if org_id is not None and org_id != workflow.org_id:
                raise ValueError("workflow_id 与 org_id 不属于同一组织")
            await membership_db.assert_org_access(
                session, user_id=actor_user_id, org_id=workflow.org_id
            )
            runs, _ = await workflow_run_db.list_workflow_runs(session, workflow_id)
        elif org_id is not None:
            await membership_db.assert_org_access(
                session, user_id=actor_user_id, org_id=org_id
            )
            runs, _ = await workflow_run_db.list_org_runs(session, org_id)
        else:
            runs = []
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [_to_run_response(run) for run in runs]


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_run(
    run_id: str,
    actor_user_id: str = Query(description="操作用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    """读取 Workflow Run。"""

    try:
        run = await workflow_run_db.get_run_required(session, run_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=run.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_run_response(run)


@router.get("/{run_id}/nodes", response_model=list[NodeRunResponse])
async def list_node_runs(
    run_id: str,
    actor_user_id: str = Query(description="操作用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[NodeRunResponse]:
    """列出 Workflow Run 节点日志。"""

    try:
        run = await workflow_run_db.get_run_required(session, run_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=run.org_id
        )
        node_runs = sorted(
            await node_run_db.list_run_node_runs(session, run_id),
            key=_node_run_sequence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [_to_node_run_response(nr, sequence=index) for index, nr in enumerate(node_runs)]


async def _submit_async_run(
    run: WorkflowRunModel,
    definition: dict[str, Any],
    request: WorkflowRunCreateRequest,
) -> None:
    """提交 Celery 异步任务。"""

    try:
        from apps.worker.app.tasks.workflow import execute_workflow

        execute_workflow.delay(
            run_id=run.run_id,
            definition=definition,
            input_data=request.input_data,
            org_id=run.org_id,
            agent_id=run.agent_id,
            actor_user_id=request.actor_user_id,
        )
    except Exception as exc:
        raise ValueError(f"异步队列不可用：{exc}") from exc


async def _execute_run_now(
    session: AsyncSession,
    run: WorkflowRunModel,
    definition: dict[str, Any],
    input_data: dict[str, Any],
    actor_user_id: str,
) -> None:
    """在 API 进程内同步执行一次 Workflow。"""

    await workflow_run_db.update_run_status(session, run.run_id, "running")
    executor = WorkflowExecutor(
        llm_gateway=lambda config, node_input: _execute_llm_node(
            session=session,
            config=config,
            node_input=node_input,
            actor_user_id=actor_user_id,
            org_id=run.org_id,
        ),
        rag_search=lambda config, node_input: _execute_rag_node(
            session=session,
            config=config,
            node_input=node_input,
            actor_user_id=actor_user_id,
            org_id=run.org_id,
        ),
        tool_call=lambda config, node_input: _execute_tool_node(
            session=session,
            config=config,
            node_input=node_input,
            actor_user_id=actor_user_id,
            org_id=run.org_id,
            agent_id=run.agent_id,
        ),
    )
    result = await executor.execute_async(definition=definition, input_data=input_data)

    for index, executed_node in enumerate(result.node_runs):
        await _persist_executed_node(session, run.run_id, executed_node, index)

    await workflow_run_db.update_run_status(
        session,
        run.run_id,
        result.status,
        output_data=result.output_data,
        error_message=result.error_message,
    )


async def _execute_llm_node(
    session: AsyncSession,
    config: dict[str, Any],
    node_input: dict[str, Any],
    actor_user_id: str,
    org_id: str,
) -> dict[str, Any]:
    """执行真实 LLM 节点。"""

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
    )
    enriched_config = {
        **config,
        "_org_id": org_id,
        "_actor_user_id": actor_user_id,
    }
    try:
        return await gateway.generate_from_workflow_node(enriched_config, node_input)
    finally:
        llm_gateway.call_logs.extend(gateway.list_logs())


async def _execute_rag_node(
    session: AsyncSession,
    config: dict[str, Any],
    node_input: dict[str, Any],
    actor_user_id: str,
    org_id: str,
) -> dict[str, Any]:
    """执行真实 RAG 节点。"""

    kb_id = str(config.get("kb_id") or "")
    if not kb_id:
        raise ValueError("RAG 节点必须选择知识库")
    kb = await knowledge_base_db.get_by_id_required(session, kb_id, "kb_id")
    if kb.org_id != org_id:
        raise ValueError("RAG 节点不能访问其他组织的知识库")

    query = _render_template(
        template=str(config.get("query_template") or ""),
        node_input=node_input,
    )
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
    session: AsyncSession,
    config: dict[str, Any],
    node_input: dict[str, Any],
    actor_user_id: str,
    org_id: str,
    agent_id: str,
) -> dict[str, Any]:
    """执行真实 Tool 节点授权校验并生成调用计划。

    MVP 阶段仍不主动请求外部 MCP Server，避免不可控副作用；但工具、授权和风险等级都来自真实接口。
    """

    tool_id = str(config.get("tool_id") or "")
    if not tool_id:
        raise ValueError("Tool 节点必须选择已授权工具")
    await membership_db.assert_org_access(
        session, user_id=actor_user_id, org_id=org_id
    )
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
    arguments = config.get("arguments", {})
    requires_approval = risk_level in {"high", "critical"}
    return {
        "tool_id": tool.tool_id,
        "tool_name": tool.name,
        "server_id": tool.server_id,
        "server_url": server.url,
        "risk_level": risk_level,
        "arguments": arguments if isinstance(arguments, dict) else {},
        "status": "requires_approval" if requires_approval else "planned",
        "requires_approval": requires_approval,
        "upstream": node_input.get("upstream", {}),
    }


async def _persist_executed_node(
    session: AsyncSession,
    run_id: str,
    executed_node: ExecutedNode,
    sequence: int,
) -> None:
    """把执行器节点结果写入数据库。"""

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


def _render_template(template: str, node_input: dict[str, Any]) -> str:
    """渲染 RAG query_template。"""

    if not template.strip():
        return ""
    workflow_input = node_input.get("workflow_input", {})
    upstream = node_input.get("upstream", {})
    rendered = template
    rendered = rendered.replace("{{input}}", _stringify_for_query(workflow_input))
    rendered = rendered.replace("{{workflow_input}}", _stringify_for_query(workflow_input))
    rendered = rendered.replace("{{upstream}}", _stringify_for_query(upstream))
    return rendered.strip()


def _stringify_for_query(value: Any) -> str:
    """把任意输入压缩成检索 query。"""

    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _to_run_response(run: WorkflowRunModel) -> WorkflowRunResponse:
    """把 WorkflowRun ORM 模型转换成 API 响应。"""

    return WorkflowRunResponse(
        run_id=run.run_id,
        org_id=run.org_id,
        workflow_id=run.workflow_id,
        version_id=run.version_id,
        agent_id=run.agent_id,
        input_data=json.loads(run.input_data),
        status=run.status,
        output_data=json.loads(run.output_data),
        error_message=run.error_message or "",
        celery_task_id="",
        created_by=run.created_by,
    )


def _node_run_sequence(nr: NodeRunModel) -> int:
    try:
        return int(nr.node_run_id.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def _to_node_run_response(nr: NodeRunModel, sequence: int = 0) -> NodeRunResponse:
    """把 NodeRun ORM 模型转换成 API 响应。"""

    return NodeRunResponse(
        node_run_id=nr.node_run_id,
        run_id=nr.run_id,
        node_id=nr.node_id,
        node_type=nr.node_type,
        status=nr.status,
        input_data=json.loads(nr.input_data),
        output_data=json.loads(nr.output_data),
        error_message=nr.error_message or "",
        elapsed_ms=nr.elapsed_ms,
        sequence=sequence,
    )
