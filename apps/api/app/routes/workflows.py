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
    WorkflowResponse,
    WorkflowUpdateDraftRequest,
    WorkflowVersionResponse,
)
from app.services.db.workflow_db import workflow_db, workflow_version_db
from app.services.db.agent_db import agent_db
from app.services.db.identity_db import membership_db
from app.domain.identity import new_id
from packages.workflow.validator import WorkflowValidator

router = APIRouter()


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

        # DAG 校验
        draft = await workflow_db.get_draft_definition(session, workflow_id)
        validator = WorkflowValidator()
        from packages.workflow.dsl import WorkflowDefinition, WorkflowNode, WorkflowEdge
        nodes = [
            WorkflowNode(
                node_id=str(node["id"]),
                node_type=str(node["type"]),
                config=dict(node.get("config", {})),
            )
            for node in draft.get("nodes", [])
        ]
        edges = [
            WorkflowEdge(source=str(edge["source"]), target=str(edge["target"]))
            for edge in draft.get("edges", [])
        ]
        wf_def = WorkflowDefinition(
            version=str(draft.get("version", "1.0")), nodes=nodes, edges=edges
        )
        validation_result = validator.validate(wf_def)
        if not validation_result["valid"]:
            raise ValueError("; ".join(validation_result["errors"]))

        version_number = await workflow_version_db.next_version_number(session, workflow_id)
        version = await workflow_version_db.create_version(
            session,
            version_id=new_id("wfv"),
            workflow_id=workflow_id,
            org_id=workflow.org_id,
            version_number=version_number,
            definition=draft,
            created_by=request.actor_user_id,
        )

        await workflow_db.set_published_version(session, workflow_id, version.version_id)
        await session.commit()

        return _to_version_response(version)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        created_by=version.created_by,
    )
