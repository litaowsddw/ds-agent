"""Workflow API（数据库版本）。

使用 SQLAlchemy 异步数据库服务替代内存 store。
"""

import json
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.workflow import WorkflowModel, WorkflowVersionModel
from app.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowPublishRequest,
    WorkflowRestoreDraftRequest,
    WorkflowResponse,
    WorkflowUpdateDraftRequest,
    WorkflowValidateRequest,
    WorkflowValidationResponse,
    WorkflowVersionResponse,
)
from app.services.db.workflow_db import workflow_db, workflow_version_db
from app.services.db.agent_db import agent_db
from app.services.db.identity_db import membership_db
from app.domain.identity import new_id
from packages.workflow.validator import WorkflowValidator
from packages.workflow.dsl import WorkflowDefinition, WorkflowEdge, WorkflowNode

router = APIRouter()


def _validate_draft_definition(draft: dict[str, object]) -> dict[str, object]:
    """Build the DSL defensively so preflight and publish share one policy."""

    raw_nodes = draft.get("nodes", [])
    raw_edges = draft.get("edges", [])
    errors: list[str] = []
    if not isinstance(raw_nodes, list):
        errors.append("nodes 必须是数组")
        raw_nodes = []
    if not isinstance(raw_edges, list):
        errors.append("edges 必须是数组")
        raw_edges = []

    nodes: list[WorkflowNode] = []
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            errors.append(f"第 {index + 1} 个节点必须是对象")
            continue
        node_id = str(node.get("id") or "").strip()
        node_type = str(node.get("type") or "").strip()
        config = node.get("config", {})
        if not node_id:
            errors.append(f"第 {index + 1} 个节点缺少 id")
            continue
        if not node_type:
            errors.append(f"节点 {node_id} 缺少类型")
            continue
        if not isinstance(config, dict):
            errors.append(f"节点 {node_id} 的 config 必须是对象")
            continue
        nodes.append(WorkflowNode(node_id=node_id, node_type=node_type, config=config))

    edges: list[WorkflowEdge] = []
    for index, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            errors.append(f"第 {index + 1} 条连线必须是对象")
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if not source or not target:
            errors.append(f"第 {index + 1} 条连线必须包含 source 和 target")
            continue
        edges.append(WorkflowEdge(source=source, target=target))

    result = WorkflowValidator().validate(
        WorkflowDefinition(version=str(draft.get("version", "1.0")), nodes=nodes, edges=edges)
    )
    return {"valid": not errors and bool(result["valid"]), "errors": [*errors, *list(result["errors"])]}


@router.post("", response_model=WorkflowResponse)
async def create_workflow(
    request: WorkflowCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    """创建 Workflow 草稿。"""
    try:
        agent = await agent_db.get_agent_required(session, request.agent_id)
        await membership_db.assert_org_access(
            session, user_id=request.actor_user_id, org_id=agent.org_id
        )

        workflow = await workflow_db.create_workflow(
            session,
            workflow_id=new_id("wfl"),
            org_id=agent.org_id,
            agent_id=agent.agent_id,
            name=request.name,
            description=request.description,
            draft_definition=request.draft_definition,
            created_by=request.actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_workflow_response(workflow)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    actor_user_id: str = Query(description="操作者用户 ID"),
    org_id: str | None = Query(default=None, description="组织 ID"),
    agent_id: str | None = Query(default=None, description="Agent ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowResponse]:
    """列出用户可访问的 Workflow。"""
    if org_id is None and agent_id is None:
        raise HTTPException(status_code=400, detail="org_id or agent_id is required")

    try:
        effective_org_id = org_id
        if agent_id is not None:
            agent = await agent_db.get_agent_required(session, agent_id)
            if org_id is not None and org_id != agent.org_id:
                raise ValueError("agent_id 与 org_id 不属于同一组织")
            await membership_db.assert_org_access(
                session, user_id=actor_user_id, org_id=agent.org_id
            )
            effective_org_id = agent.org_id
        elif org_id is not None:
            await membership_db.assert_org_access(
                session, user_id=actor_user_id, org_id=org_id
            )
        workflows, _ = await workflow_db.list_workflows(
            session, org_id=effective_org_id, agent_id=agent_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_workflow_response(w) for w in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    """读取 Workflow。"""
    try:
        workflow = await workflow_db.get_workflow_required(session, workflow_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=workflow.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_workflow_response(workflow)


@router.put("/{workflow_id}/draft", response_model=WorkflowResponse)
async def update_draft(
    workflow_id: str,
    request: WorkflowUpdateDraftRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    """更新 Workflow 草稿。"""
    try:
        workflow = await workflow_db.get_workflow_required(session, workflow_id)
        await membership_db.assert_org_access(
            session, user_id=request.actor_user_id, org_id=workflow.org_id
        )
        workflow = await workflow_db.update_draft(
            session, workflow_id, request.draft_definition
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _to_workflow_response(workflow)


@router.post("/{workflow_id}/validate", response_model=WorkflowValidationResponse)
async def validate_workflow_draft(
    workflow_id: str,
    request: WorkflowValidateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowValidationResponse:
    """Validate the caller's current canvas before they save, publish, or run it."""

    try:
        workflow = await workflow_db.get_workflow_required(session, workflow_id)
        await membership_db.assert_org_access(
            session, user_id=request.actor_user_id, org_id=workflow.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = _validate_draft_definition(request.draft_definition)
    return WorkflowValidationResponse(valid=bool(result["valid"]), errors=list(result["errors"]))


@router.post("/{workflow_id}/publish", response_model=WorkflowVersionResponse)
async def publish_workflow(
    workflow_id: str,
    request: WorkflowPublishRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowVersionResponse:
    """发布 Workflow 版本。"""
    try:
        workflow = await workflow_db.get_workflow_required(session, workflow_id)
        await membership_db.assert_org_access(
            session, user_id=request.actor_user_id, org_id=workflow.org_id
        )

        draft = await workflow_db.get_draft_definition(session, workflow_id)
        validation_result = _validate_draft_definition(draft)
        if not validation_result["valid"]:
            raise ValueError("；".join(validation_result["errors"]))

        version_number = await workflow_version_db.next_version_number(session, workflow_id)
        version = await workflow_version_db.create_version(
            session,
            version_id=new_id("wfv"),
            workflow_id=workflow_id,
            org_id=workflow.org_id,
            version_number=version_number,
            definition=draft,
            release_note=request.release_note,
            created_by=request.actor_user_id,
        )

        await workflow_db.set_published_version(session, workflow_id, version.version_id)
        await session.commit()

        return _to_version_response(version)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{workflow_id}/versions/{version_id}/restore-draft", response_model=WorkflowResponse)
async def restore_version_to_draft(
    workflow_id: str,
    version_id: str,
    request: WorkflowRestoreDraftRequest,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    """Copy an immutable published snapshot into the editable draft.

    The currently live ``published_version_id`` is deliberately left untouched:
    a restore is a safe preparation step that must pass preflight and be
    explicitly published before production traffic changes.
    """

    try:
        workflow = await workflow_db.get_workflow_required(session, workflow_id)
        await membership_db.assert_org_access(
            session, user_id=request.actor_user_id, org_id=workflow.org_id
        )
        version = await workflow_version_db.get_workflow_version_required(
            session, workflow_id, version_id
        )
        workflow = await workflow_db.update_draft(
            session, workflow_id, json.loads(version.definition)
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_workflow_response(workflow)


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionResponse])
async def list_versions(
    workflow_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowVersionResponse]:
    """列出 Workflow 发布版本。"""
    try:
        workflow = await workflow_db.get_workflow_required(session, workflow_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=workflow.org_id
        )
        versions = await workflow_version_db.list_workflow_versions(session, workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [_to_version_response(v) for v in versions]


def _to_workflow_response(workflow: WorkflowModel) -> WorkflowResponse:
    """把 Workflow ORM 模型转换为 API 响应。"""
    return WorkflowResponse(
        workflow_id=workflow.workflow_id,
        org_id=workflow.org_id,
        agent_id=workflow.agent_id,
        name=workflow.name,
        description=workflow.description or "",
        draft_definition=json.loads(workflow.draft_definition),
        published_version_id=workflow.published_version_id,
        created_by=workflow.created_by,
    )


def _to_version_response(version: WorkflowVersionModel) -> WorkflowVersionResponse:
    """把 WorkflowVersion ORM 模型转换为 API 响应。"""
    return WorkflowVersionResponse(
        version_id=version.version_id,
        workflow_id=version.workflow_id,
        org_id="",
        version_number=version.version_number,
        definition=json.loads(version.definition),
        release_note=version.release_note or "",
        created_by=version.created_by,
        created_at=version.created_at,
    )
