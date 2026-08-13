"""Workflow Run API。

这个路由负责 Workflow Run 的 HTTP 契约、鉴权和响应转换。
真实执行逻辑集中在 workflow_execution_service，供 API 与 Chat 流程模式复用。
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.database import get_db_session
from app.domain.identity import new_id
from app.models.workflow import NodeRunModel, WorkflowApprovalRequestModel, WorkflowRunModel
from app.schemas.workflow_run import (
    NodeRunResponse,
    WorkflowApprovalDecisionRequest,
    WorkflowApprovalResponse,
    WorkflowRunCreateRequest,
    WorkflowRunResponse,
)
from app.services.db.identity_db import membership_db
from app.services.db.workflow_db import (
    node_run_db,
    workflow_approval_db,
    workflow_db,
    workflow_run_db,
    workflow_version_db,
)
from app.services.workflow_execution import workflow_execution_service

router = APIRouter()


@dataclass(frozen=True, slots=True)
class WorkflowChatStreamUpdate:
    """One chat-only Workflow execution update."""

    kind: Literal["usage", "completed"]
    event_name: str = ""
    payload: dict[str, object] = field(default_factory=dict)
    run: WorkflowRunModel | None = None


def _require_server_authenticated_identity(auth: AuthenticatedUser) -> None:
    if not auth.email:
        raise HTTPException(status_code=401, detail="Bearer token or service API key required")


@router.post("", response_model=WorkflowRunResponse)
async def create_run(
    request: WorkflowRunCreateRequest,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    """创建并执行 Workflow Run。"""

    try:
        _require_server_authenticated_identity(auth)
        version = await workflow_version_db.get_by_id_required(
            session, request.version_id, "version_id"
        )
        workflow = await workflow_db.get_workflow_required(session, version.workflow_id)
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=workflow.org_id
        )

        if request.async_mode:
            run = await workflow_run_db.create_run(
                session,
                run_id=new_id("run"),
                workflow_id=workflow.workflow_id,
                version_id=version.version_id,
                org_id=workflow.org_id,
                agent_id=workflow.agent_id,
                created_by=auth.user_id,
                input_data=request.input_data,
            )
            await session.commit()
            await _submit_async_run(run=run)
        else:
            run = await workflow_execution_service.create_and_execute(
                session,
                version_id=version.version_id,
                input_data=request.input_data,
                actor_user_id=auth.user_id,
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

    return await workflow_execution_service.create_and_execute(
        session,
        version_id=version_id,
        input_data=input_data,
        actor_user_id=actor_user_id,
    )


async def stream_workflow_version_for_chat(
    session: AsyncSession,
    *,
    version_id: str,
    input_data: dict[str, Any],
    actor_user_id: str,
    token_limit: int,
) -> AsyncIterator[WorkflowChatStreamUpdate]:
    """Execute a Workflow while forwarding its LLM usage to chat only."""

    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

    async def on_usage_event(payload: dict[str, object]) -> None:
        payload["token_limit"] = token_limit
        await queue.put(payload)

    task = asyncio.create_task(
        workflow_execution_service.create_and_execute(
            session,
            version_id=version_id,
            input_data=input_data,
            actor_user_id=actor_user_id,
            on_usage_event=on_usage_event,
        )
    )
    try:
        while not task.done() or not queue.empty():
            next_payload = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {task, next_payload},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if next_payload not in done:
                next_payload.cancel()
                with suppress(asyncio.CancelledError):
                    await next_payload
                continue
            payload = next_payload.result()
            phase = str(payload["usage_phase"])
            event_name = (
                "context_preflight"
                if phase == "preflight"
                else "context_progress"
                if phase == "estimated"
                else "context_usage"
            )
            yield WorkflowChatStreamUpdate("usage", event_name, payload)
        yield WorkflowChatStreamUpdate("completed", run=await task)
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@router.get("", response_model=list[WorkflowRunResponse])
async def list_runs(
    auth: AuthenticatedUser,
    workflow_id: str | None = Query(default=None, description="Workflow ID"),
    org_id: str | None = Query(default=None, description="Organization ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowRunResponse]:
    """列出用户可访问的 Workflow Run。"""
    # 缺过滤条件时按 JWT 中的组织过滤，不再静默返回空列表造成“数据丢失”假象
    effective_org_id = org_id or auth.org_id
    try:
        if workflow_id is not None:
            workflow = await workflow_db.get_workflow_required(session, workflow_id)
            if org_id is not None and org_id != workflow.org_id:
                raise ValueError("workflow_id 与 org_id 不属于同一组织")
            await membership_db.assert_org_access(
                session, user_id=auth.user_id, org_id=workflow.org_id
            )
            runs, _ = await workflow_run_db.list_workflow_runs(session, workflow_id)
        elif effective_org_id is not None:
            await membership_db.assert_org_access(
                session, user_id=auth.user_id, org_id=effective_org_id
            )
            runs, _ = await workflow_run_db.list_org_runs(session, effective_org_id)
        else:
            raise HTTPException(status_code=400, detail="缺少 workflow_id 或 org_id 过滤条件")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_run_response(run) for run in runs]


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_run(
    run_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    """读取 Workflow Run。"""

    try:
        run = await workflow_run_db.get_run_required(session, run_id)
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=run.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_run_response(run)


@router.get("/{run_id}/nodes", response_model=list[NodeRunResponse])
async def list_node_runs(
    run_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[NodeRunResponse]:
    """列出 Workflow Run 节点日志。"""

    try:
        run = await workflow_run_db.get_run_required(session, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=run.org_id
        )
    except ValueError as exc:
        # The run exists, so never disguise a cross-organization denial as a
        # missing resource or reveal membership details.
        raise HTTPException(status_code=403, detail="Forbidden") from exc

    node_runs = sorted(
        await node_run_db.list_run_node_runs(session, run_id),
        key=_node_run_sequence,
    )

    return [_to_node_run_response(nr, sequence=index) for index, nr in enumerate(node_runs)]


@router.get("/{run_id}/approvals", response_model=list[WorkflowApprovalResponse])
async def list_run_approvals(
    run_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowApprovalResponse]:
    """List redacted high-risk Tool approval requests for organization operators."""

    try:
        _require_server_authenticated_identity(auth)
        run = await workflow_run_db.get_run_required(session, run_id)
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=run.org_id, required_role="admin"
        )
        approvals = await workflow_approval_db.list_run_approvals(session, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    return [_to_approval_response(approval) for approval in approvals]


@router.post(
    "/{run_id}/approvals/{approval_id}/decision",
    response_model=WorkflowApprovalResponse,
)
async def decide_run_approval(
    run_id: str,
    approval_id: str,
    request: WorkflowApprovalDecisionRequest,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowApprovalResponse:
    """Approve or reject exactly one durable high-risk MCP Tool action."""

    try:
        _require_server_authenticated_identity(auth)
        run = await workflow_run_db.get_run_required(session, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc
    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=run.org_id, required_role="admin"
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    try:
        approval = await workflow_execution_service.decide_high_risk_tool_approval(
            session,
            run=run,
            approval_id=approval_id,
            decision=request.decision,
            actor_user_id=auth.user_id,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _to_approval_response(approval)


@router.post("/{run_id}/resume", response_model=WorkflowRunResponse)
async def resume_run(
    run_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    """审批通过后从暂停点续跑剩余 DAG 节点并落盘。"""

    try:
        _require_server_authenticated_identity(auth)
        run = await workflow_run_db.get_run_required(session, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc
    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=run.org_id, required_role="admin"
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    try:
        run = await workflow_execution_service.resume_existing_run(
            session,
            run=run,
            actor_user_id=auth.user_id,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _to_run_response(run)


async def _submit_async_run(
    run: WorkflowRunModel,
) -> None:
    """提交 Celery 异步任务。"""

    try:
        from apps.worker.app.tasks.workflow import execute_workflow

        execute_workflow.delay(
            run_id=run.run_id,
        )
    except Exception as exc:
        raise ValueError(f"异步队列不可用：{exc}") from exc


def _to_run_response(run: WorkflowRunModel) -> WorkflowRunResponse:
    """把 WorkflowRun ORM 模型转换成 API 响应。"""

    # Workflow runs predate the generic ``updated_at`` column used by several
    # other resources.  Their lifecycle is already recorded explicitly, so
    # expose the real lifecycle timestamps instead of leaving the Runs page
    # with a permanently empty "last updated" field.
    started_at = getattr(run, "started_at", None)
    finished_at = getattr(run, "finished_at", None)
    updated_at = getattr(run, "updated_at", None) or finished_at or started_at

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
        created_at=run.created_at,
        started_at=started_at,
        finished_at=finished_at,
        updated_at=updated_at,
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


def _to_approval_response(approval: WorkflowApprovalRequestModel) -> WorkflowApprovalResponse:
    """Never serialize the encrypted executable parameter envelope."""

    return WorkflowApprovalResponse(
        approval_id=approval.approval_id,
        run_id=approval.run_id,
        node_id=approval.node_id,
        tool_id=approval.tool_id,
        server_id=approval.server_id,
        tool_name=approval.tool_name,
        risk_level=approval.risk_level,
        arguments=json.loads(approval.arguments_redacted),
        status=approval.status,
        requested_by=approval.requested_by,
        decided_by=approval.decided_by,
        decided_at=approval.decided_at,
        execution_node_run_id=approval.execution_node_run_id,
        error_message=approval.error_message or "",
        created_at=approval.created_at,
    )
