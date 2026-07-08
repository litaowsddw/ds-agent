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
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity import new_id
from app.gateway.llm import OpenAICompatibleProvider
from app.models.workflow import NodeRunModel, WorkflowRunModel
from app.schemas.workflow_run import (
    NodeRunResponse,
    WorkflowRunCreateRequest,
    WorkflowRunResponse,
)
from app.services.db.identity_db import membership_db
from app.services.db.workflow_db import (
    workflow_db,
    workflow_run_db,
    workflow_version_db,
)
from app.services import workflow_execution as workflow_execution_module
from app.services.workflow_execution import workflow_execution_service

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

        definition = json.loads(version.definition)
        if request.async_mode:
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
            await _submit_async_run(run=run, definition=definition, request=request)
        else:
            workflow_execution_module.OpenAICompatibleProvider = OpenAICompatibleProvider
            run = await workflow_execution_service.create_and_execute(
                session,
                version_id=version.version_id,
                input_data=request.input_data,
                actor_user_id=request.actor_user_id,
            )
            await session.commit()

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

    workflow_execution_module.OpenAICompatibleProvider = OpenAICompatibleProvider
    return await workflow_execution_service.create_and_execute(
        session,
        version_id=version_id,
        input_data=input_data,
        actor_user_id=actor_user_id,
    )


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
