"""Workflow API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.workflow import Workflow, WorkflowVersion
from apps.api.app.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowPublishRequest,
    WorkflowResponse,
    WorkflowUpdateDraftRequest,
    WorkflowVersionResponse,
)
from apps.api.app.services.workflow_store import workflow_store

router = APIRouter()


@router.post("", response_model=WorkflowResponse)
async def create_workflow(request: WorkflowCreateRequest) -> WorkflowResponse:
    """创建 Workflow 草稿。"""

    try:
        workflow = workflow_store.create_workflow(
            actor_user_id=request.actor_user_id,
            agent_id=request.agent_id,
            name=request.name,
            description=request.description,
            draft_definition=request.draft_definition,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_workflow_response(workflow)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    actor_user_id: str = Query(description="操作者用户 ID"),
    org_id: str | None = Query(default=None, description="组织 ID"),
    agent_id: str | None = Query(default=None, description="Agent ID"),
) -> list[WorkflowResponse]:
    """列出用户可访问的 Workflow。"""

    try:
        workflows = workflow_store.list_workflows(
            actor_user_id=actor_user_id,
            org_id=org_id,
            agent_id=agent_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return [_to_workflow_response(workflow) for workflow in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> WorkflowResponse:
    """读取 Workflow。"""

    try:
        workflow = workflow_store.get_workflow(actor_user_id=actor_user_id, workflow_id=workflow_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_workflow_response(workflow)


@router.put("/{workflow_id}/draft", response_model=WorkflowResponse)
async def update_draft(workflow_id: str, request: WorkflowUpdateDraftRequest) -> WorkflowResponse:
    """更新 Workflow 草稿。"""

    try:
        workflow = workflow_store.update_draft(
            actor_user_id=request.actor_user_id,
            workflow_id=workflow_id,
            draft_definition=request.draft_definition,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_workflow_response(workflow)


@router.post("/{workflow_id}/publish", response_model=WorkflowVersionResponse)
async def publish_workflow(
    workflow_id: str, request: WorkflowPublishRequest
) -> WorkflowVersionResponse:
    """发布 Workflow 版本。"""

    try:
        version = workflow_store.publish(
            actor_user_id=request.actor_user_id, workflow_id=workflow_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_version_response(version)


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionResponse])
async def list_versions(
    workflow_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[WorkflowVersionResponse]:
    """列出 Workflow 发布版本。"""

    try:
        versions = workflow_store.list_versions(
            actor_user_id=actor_user_id, workflow_id=workflow_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [_to_version_response(version) for version in versions]


def _to_workflow_response(workflow: Workflow) -> WorkflowResponse:
    """把 Workflow 领域模型转换为 API 响应。"""

    return WorkflowResponse(
        workflow_id=workflow.workflow_id,
        org_id=workflow.org_id,
        agent_id=workflow.agent_id,
        name=workflow.name,
        description=workflow.description,
        draft_definition=workflow.draft_definition,
        published_version_id=workflow.published_version_id,
        created_by=workflow.created_by,
    )


def _to_version_response(version: WorkflowVersion) -> WorkflowVersionResponse:
    """把 WorkflowVersion 领域模型转换为 API 响应。"""

    return WorkflowVersionResponse(
        version_id=version.version_id,
        workflow_id=version.workflow_id,
        org_id=version.org_id,
        version_number=version.version_number,
        definition=version.definition,
        created_by=version.created_by,
    )
