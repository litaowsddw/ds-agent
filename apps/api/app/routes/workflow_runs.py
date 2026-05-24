"""Workflow Run API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.workflow_run import NodeRun, WorkflowRun
from apps.api.app.schemas.workflow_run import (
    NodeRunResponse,
    WorkflowRunCreateRequest,
    WorkflowRunResponse,
)
from apps.api.app.services.workflow_run_store import workflow_run_store
from apps.api.app.services.workflow_store import workflow_store
from apps.worker.app.tasks.workflow import execute_workflow

router = APIRouter()


@router.post("", response_model=WorkflowRunResponse)
async def create_run(request: WorkflowRunCreateRequest) -> WorkflowRunResponse:
    """创建 Workflow Run。"""

    try:
        run = workflow_run_store.create_run(
            actor_user_id=request.actor_user_id,
            version_id=request.version_id,
            input_data=request.input_data,
            execute_immediately=not request.async_mode,
        )

        if request.async_mode:
            version = workflow_store.get_version(
                actor_user_id=request.actor_user_id,
                version_id=request.version_id,
            )
            celery_result = execute_workflow.delay(
                definition=version.definition,
                input_data=request.input_data,
            )
            run = workflow_run_store.attach_celery_task(
                actor_user_id=request.actor_user_id,
                run_id=run.run_id,
                celery_task_id=celery_result.id,
            )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_run_response(run)


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_run(
    run_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> WorkflowRunResponse:
    """读取 Workflow Run。"""

    try:
        run = workflow_run_store.get_run(actor_user_id=actor_user_id, run_id=run_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_run_response(run)


@router.get("/{run_id}/nodes", response_model=list[NodeRunResponse])
async def list_node_runs(
    run_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[NodeRunResponse]:
    """列出 Workflow Run 节点日志。"""

    try:
        node_runs = workflow_run_store.list_node_runs(actor_user_id=actor_user_id, run_id=run_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [_to_node_run_response(node_run) for node_run in node_runs]


def _to_run_response(run: WorkflowRun) -> WorkflowRunResponse:
    """把 WorkflowRun 领域模型转换为 API 响应。"""

    return WorkflowRunResponse(
        run_id=run.run_id,
        org_id=run.org_id,
        workflow_id=run.workflow_id,
        version_id=run.version_id,
        agent_id=run.agent_id,
        input_data=run.input_data,
        status=run.status,
        output_data=run.output_data,
        error_message=run.error_message,
        celery_task_id=run.celery_task_id,
        created_by=run.created_by,
    )


def _to_node_run_response(node_run: NodeRun) -> NodeRunResponse:
    """把 NodeRun 领域模型转换为 API 响应。"""

    return NodeRunResponse(
        node_run_id=node_run.node_run_id,
        run_id=node_run.run_id,
        node_id=node_run.node_id,
        node_type=node_run.node_type,
        status=node_run.status,
        input_data=node_run.input_data,
        output_data=node_run.output_data,
        error_message=node_run.error_message,
        elapsed_ms=node_run.elapsed_ms,
        sequence=node_run.sequence,
    )

