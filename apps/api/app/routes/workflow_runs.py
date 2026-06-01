"""Workflow Run API（数据库版本）。

使用 SQLAlchemy 异步数据库服务替代内存 store。
"""

import json
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.workflow import WorkflowRunModel, NodeRunModel
from app.schemas.workflow_run import (
    NodeRunResponse,
    WorkflowRunCreateRequest,
    WorkflowRunResponse,
)
from app.services.db.workflow_db import workflow_run_db, node_run_db, workflow_version_db, workflow_db
from app.services.db.identity_db import membership_db
from app.domain.identity import new_id

router = APIRouter()


@router.post("", response_model=WorkflowRunResponse)
async def create_run(
    request: WorkflowRunCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunResponse:
    """创建 Workflow Run。"""
    try:
        # 校验版本存在
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

        # 异步模式：提交 Celery 任务
        if request.async_mode:
            try:
                from apps.worker.app.tasks.workflow import execute_workflow
                definition = json.loads(version.definition)
                execute_workflow.delay(
                    run_id=run.run_id,
                    definition=definition,
                    input_data=request.input_data,
                    org_id=workflow.org_id,
                    agent_id=workflow.agent_id,
                )
            except Exception:
                # Celery 不可用时同步执行
                pass

    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_run_response(run)


@router.get("", response_model=list[WorkflowRunResponse])
async def list_runs(
    actor_user_id: str = Query(description="操作者用户 ID"),
    workflow_id: str | None = Query(default=None, description="Workflow ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowRunResponse]:
    """列出用户可访问的 Workflow Run。"""
    if workflow_id is not None:
        runs, _ = await workflow_run_db.list_workflow_runs(session, workflow_id)
    else:
        runs = []
    return [_to_run_response(run) for run in runs]


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_run(
    run_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
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
    actor_user_id: str = Query(description="操作者用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[NodeRunResponse]:
    """列出 Workflow Run 节点日志。"""
    try:
        run = await workflow_run_db.get_run_required(session, run_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=run.org_id
        )
        node_runs = await node_run_db.list_run_node_runs(session, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [_to_node_run_response(nr) for nr in node_runs]


def _to_run_response(run: WorkflowRunModel) -> WorkflowRunResponse:
    """把 WorkflowRun ORM 模型转换为 API 响应。"""
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


def _to_node_run_response(nr: NodeRunModel) -> NodeRunResponse:
    """把 NodeRun ORM 模型转换为 API 响应。"""
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
        sequence=0,
    )
