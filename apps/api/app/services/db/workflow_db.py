"""Workflow 数据库服务。

替换 workflow_store.py 和 workflow_run_store.py 的内存实现，
使用 SQLAlchemy 异步操作 MySQL。
"""

import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    WorkflowModel,
    WorkflowVersionModel,
    WorkflowRunModel,
    NodeRunModel,
    WorkflowApprovalRequestModel,
    KnowledgeBaseModel,
    DocumentModel,
    ChunkModel,
)
from app.services.db.base import BaseDBService


class WorkflowDBService(BaseDBService[WorkflowModel]):
    """Workflow 数据库服务。"""

    def __init__(self) -> None:
        super().__init__(WorkflowModel)

    async def create_workflow(
        self,
        session: AsyncSession,
        workflow_id: str,
        org_id: str,
        agent_id: str,
        name: str,
        description: str = "",
        draft_definition: dict | None = None,
        created_by: str = "",
    ) -> WorkflowModel:
        """创建 Workflow。"""
        workflow = WorkflowModel(
            workflow_id=workflow_id,
            org_id=org_id,
            agent_id=agent_id,
            name=name.strip(),
            description=description.strip(),
            draft_definition=json.dumps(draft_definition or {}, ensure_ascii=False),
            created_by=created_by,
        )
        session.add(workflow)
        await session.flush()
        return workflow

    async def get_workflow_required(self, session: AsyncSession, workflow_id: str) -> WorkflowModel:
        """获取 Workflow，不存在则抛出异常。"""
        return await self.get_by_id_required(session, workflow_id, "workflow_id")

    async def list_workflows(
        self,
        session: AsyncSession,
        org_id: str | None = None,
        agent_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[WorkflowModel], int]:
        """列出 Workflow。"""
        filters = {}
        if org_id is not None:
            filters["org_id"] = org_id
        if agent_id is not None:
            filters["agent_id"] = agent_id
        return await self.list_paginated(session, offset=offset, limit=limit, **filters)

    async def update_draft(
        self,
        session: AsyncSession,
        workflow_id: str,
        draft_definition: dict,
    ) -> WorkflowModel:
        """更新 Workflow 草稿。"""
        workflow = await self.get_workflow_required(session, workflow_id)
        workflow.draft_definition = json.dumps(draft_definition, ensure_ascii=False)
        workflow.updated_at = datetime.utcnow()
        await session.flush()
        return workflow

    async def set_published_version(
        self,
        session: AsyncSession,
        workflow_id: str,
        version_id: str,
    ) -> WorkflowModel:
        """设置发布版本。"""
        workflow = await self.get_workflow_required(session, workflow_id)
        workflow.published_version_id = version_id
        workflow.updated_at = datetime.utcnow()
        await session.flush()
        return workflow

    async def get_draft_definition(
        self, session: AsyncSession, workflow_id: str
    ) -> dict:
        """获取草稿定义（解析 JSON）。"""
        workflow = await self.get_workflow_required(session, workflow_id)
        return json.loads(workflow.draft_definition)


class WorkflowVersionDBService(BaseDBService[WorkflowVersionModel]):
    """Workflow 版本数据库服务。"""

    def __init__(self) -> None:
        super().__init__(WorkflowVersionModel)

    async def create_version(
        self,
        session: AsyncSession,
        version_id: str,
        workflow_id: str,
        org_id: str,
        version_number: int,
        definition: dict,
        release_note: str = "",
        created_by: str = "",
    ) -> WorkflowVersionModel:
        """创建发布版本（不可变）。"""
        version = WorkflowVersionModel(
            version_id=version_id,
            workflow_id=workflow_id,
            version_number=version_number,
            definition=json.dumps(definition, ensure_ascii=False),
            release_note=release_note.strip(),
            created_by=created_by,
        )
        session.add(version)
        await session.flush()
        return version

    async def list_workflow_versions(
        self,
        session: AsyncSession,
        workflow_id: str,
    ) -> list[WorkflowVersionModel]:
        """列出 Workflow 的发布版本。"""
        stmt = (
            select(WorkflowVersionModel)
            .where(WorkflowVersionModel.workflow_id == workflow_id)
            .order_by(WorkflowVersionModel.version_number)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def next_version_number(self, session: AsyncSession, workflow_id: str) -> int:
        """计算下一个版本号。"""
        stmt = select(func.max(WorkflowVersionModel.version_number)).where(
            WorkflowVersionModel.workflow_id == workflow_id
        )
        result = await session.execute(stmt)
        max_version = result.scalar()
        return (max_version or 0) + 1

    async def get_version_definition(
        self, session: AsyncSession, version_id: str
    ) -> dict:
        """获取版本定义（解析 JSON）。"""
        version = await self.get_by_id_required(session, version_id, "version_id")
        return json.loads(version.definition)

    async def get_workflow_version_required(
        self,
        session: AsyncSession,
        workflow_id: str,
        version_id: str,
    ) -> WorkflowVersionModel:
        """Return a version only when it belongs to the requested workflow.

        Keeping this lookup scoped prevents a caller from restoring a snapshot
        that belongs to another workflow in the same organization.
        """

        version = await self.get_by_id_required(session, version_id, "version_id")
        if version.workflow_id != workflow_id:
            raise ValueError("该发布版本不属于当前 Workflow")
        return version


class WorkflowRunDBService(BaseDBService[WorkflowRunModel]):
    """Workflow 运行数据库服务。"""

    def __init__(self) -> None:
        super().__init__(WorkflowRunModel)

    async def create_run(
        self,
        session: AsyncSession,
        run_id: str,
        workflow_id: str,
        version_id: str,
        org_id: str,
        agent_id: str,
        created_by: str = "",
        input_data: dict | None = None,
    ) -> WorkflowRunModel:
        """创建 Workflow 运行。"""
        run = WorkflowRunModel(
            run_id=run_id,
            workflow_id=workflow_id,
            version_id=version_id,
            org_id=org_id,
            agent_id=agent_id,
            status="pending",
            input_data=json.dumps(input_data or {}, ensure_ascii=False),
            created_by=created_by,
        )
        session.add(run)
        await session.flush()
        return run

    async def get_run_required(self, session: AsyncSession, run_id: str) -> WorkflowRunModel:
        """获取运行记录。"""
        return await self.get_by_id_required(session, run_id, "run_id")

    async def update_run_status(
        self,
        session: AsyncSession,
        run_id: str,
        status: str,
        output_data: dict | None = None,
        error_message: str = "",
    ) -> WorkflowRunModel:
        """更新运行状态。"""
        run = await self.get_run_required(session, run_id)
        run.status = status
        if output_data is not None:
            run.output_data = json.dumps(output_data, ensure_ascii=False)
        if error_message:
            run.error_message = error_message
        now = datetime.utcnow()
        if status == "running" and run.started_at is None:
            run.started_at = now
        if status in ("succeeded", "failed", "cancelled"):
            run.finished_at = now
        await session.flush()
        return run

    async def list_workflow_runs(
        self,
        session: AsyncSession,
        workflow_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[WorkflowRunModel], int]:
        """列出 Workflow 运行。"""
        count_stmt = select(func.count()).select_from(WorkflowRunModel).where(
            WorkflowRunModel.workflow_id == workflow_id
        )
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0
        stmt = (
            select(WorkflowRunModel)
            .where(WorkflowRunModel.workflow_id == workflow_id)
            .order_by(WorkflowRunModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    async def list_org_runs(
        self,
        session: AsyncSession,
        org_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[WorkflowRunModel], int]:
        """List workflow runs in one organization for Studio run history."""
        count_stmt = select(func.count()).select_from(WorkflowRunModel).where(
            WorkflowRunModel.org_id == org_id
        )
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0
        stmt = (
            select(WorkflowRunModel)
            .where(WorkflowRunModel.org_id == org_id)
            .order_by(WorkflowRunModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total


class NodeRunDBService(BaseDBService[NodeRunModel]):
    """节点运行日志数据库服务。"""

    def __init__(self) -> None:
        super().__init__(NodeRunModel)

    async def create_node_run(
        self,
        session: AsyncSession,
        node_run_id: str,
        run_id: str,
        node_id: str,
        node_type: str,
        input_data: dict | None = None,
    ) -> NodeRunModel:
        """创建节点运行记录。"""
        node_run = NodeRunModel(
            node_run_id=node_run_id,
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            status="pending",
            input_data=json.dumps(input_data or {}, ensure_ascii=False),
        )
        session.add(node_run)
        await session.flush()
        return node_run

    async def update_node_run(
        self,
        session: AsyncSession,
        node_run_id: str,
        status: str,
        output_data: dict | None = None,
        error_message: str = "",
        elapsed_ms: int = 0,
    ) -> NodeRunModel:
        """更新节点运行状态。"""
        node_run = await self.get_by_id_required(session, node_run_id, "node_run_id")
        node_run.status = status
        if output_data is not None:
            node_run.output_data = json.dumps(output_data, ensure_ascii=False)
        if error_message:
            node_run.error_message = error_message
        node_run.elapsed_ms = elapsed_ms
        now = datetime.utcnow()
        if status == "running" and node_run.started_at is None:
            node_run.started_at = now
        if status in ("succeeded", "failed"):
            node_run.finished_at = now
        await session.flush()
        return node_run

    async def list_run_node_runs(
        self, session: AsyncSession, run_id: str
    ) -> list[NodeRunModel]:
        """列出运行的所有节点日志。"""
        stmt = (
            select(NodeRunModel)
            .where(NodeRunModel.run_id == run_id)
            .order_by(NodeRunModel.node_run_id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class WorkflowApprovalDBService(BaseDBService[WorkflowApprovalRequestModel]):
    """Persistence and state transitions for high-risk Tool approvals."""

    def __init__(self) -> None:
        super().__init__(WorkflowApprovalRequestModel)

    async def create_pending(
        self,
        session: AsyncSession,
        *,
        approval_id: str,
        run_id: str,
        org_id: str,
        node_id: str,
        tool_id: str,
        server_id: str,
        tool_name: str,
        risk_level: str,
        arguments_redacted: dict[str, Any],
        arguments_encrypted: str,
        requested_by: str,
    ) -> WorkflowApprovalRequestModel:
        approval = WorkflowApprovalRequestModel(
            approval_id=approval_id,
            run_id=run_id,
            org_id=org_id,
            node_id=node_id,
            tool_id=tool_id,
            server_id=server_id,
            tool_name=tool_name,
            risk_level=risk_level,
            arguments_redacted=json.dumps(arguments_redacted, ensure_ascii=False),
            arguments_encrypted=arguments_encrypted,
            status="pending",
            requested_by=requested_by,
        )
        session.add(approval)
        await session.flush()
        return approval

    async def list_run_approvals(
        self, session: AsyncSession, run_id: str
    ) -> list[WorkflowApprovalRequestModel]:
        result = await session.execute(
            select(WorkflowApprovalRequestModel)
            .where(WorkflowApprovalRequestModel.run_id == run_id)
            .order_by(WorkflowApprovalRequestModel.created_at)
        )
        return list(result.scalars().all())

    async def get_run_approval_required(
        self,
        session: AsyncSession,
        *,
        run_id: str,
        approval_id: str,
        for_update: bool = False,
    ) -> WorkflowApprovalRequestModel:
        statement = select(WorkflowApprovalRequestModel).where(
            WorkflowApprovalRequestModel.approval_id == approval_id,
            WorkflowApprovalRequestModel.run_id == run_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        approval = result.scalar_one_or_none()
        if approval is None:
            raise ValueError("审批请求不存在")
        return approval


class KnowledgeBaseDBService(BaseDBService[KnowledgeBaseModel]):
    """知识库数据库服务。"""

    def __init__(self) -> None:
        super().__init__(KnowledgeBaseModel)

    async def create_kb(
        self,
        session: AsyncSession,
        kb_id: str,
        org_id: str,
        name: str,
        description: str = "",
        embedding_model: str = "",
        created_by: str = "",
    ) -> KnowledgeBaseModel:
        """创建知识库。"""
        kb = KnowledgeBaseModel(
            kb_id=kb_id,
            org_id=org_id,
            name=name,
            description=description,
            embedding_model=embedding_model,
            created_by=created_by,
        )
        session.add(kb)
        await session.flush()
        return kb

    async def list_org_kbs(
        self,
        session: AsyncSession,
        org_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[KnowledgeBaseModel], int]:
        """列出组织知识库。"""
        return await self.list_paginated(session, offset=offset, limit=limit, org_id=org_id)


class DocumentDBService(BaseDBService[DocumentModel]):
    """文档数据库服务。"""

    def __init__(self) -> None:
        super().__init__(DocumentModel)

    async def create_document(
        self,
        session: AsyncSession,
        document_id: str,
        kb_id: str,
        title: str,
        content: str = "",
        created_by: str = "",
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> DocumentModel:
        """创建文档。"""
        doc = DocumentModel(
            document_id=document_id,
            kb_id=kb_id,
            title=title,
            content=content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            created_by=created_by,
        )
        session.add(doc)
        await session.flush()
        return doc

    async def list_kb_documents(
        self,
        session: AsyncSession,
        kb_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[DocumentModel], int]:
        """列出知识库文档。"""
        return await self.list_paginated(session, offset=offset, limit=limit, kb_id=kb_id)

    async def update_status(
        self, session: AsyncSession, document_id: str, status: str
    ) -> DocumentModel:
        """更新文档状态。"""
        doc = await self.get_by_id_required(session, document_id, "document_id")
        doc.status = status
        await session.flush()
        return doc


class ChunkDBService(BaseDBService[ChunkModel]):
    """文档块数据库服务。"""

    def __init__(self) -> None:
        super().__init__(ChunkModel)

    async def create_chunk(
        self,
        session: AsyncSession,
        chunk_id: str,
        document_id: str,
        content: str,
        sequence: int,
        estimated_tokens: int = 0,
        embedding_model: str = "",
    ) -> ChunkModel:
        """创建文档块。"""
        chunk = ChunkModel(
            chunk_id=chunk_id,
            document_id=document_id,
            content=content,
            sequence=sequence,
            estimated_tokens=estimated_tokens,
            embedding_model=embedding_model,
        )
        session.add(chunk)
        await session.flush()
        return chunk

    async def batch_create_chunks(
        self, session: AsyncSession, chunks: list[dict]
    ) -> list[ChunkModel]:
        """批量创建文档块。"""
        models = []
        for chunk_data in chunks:
            chunk = ChunkModel(**chunk_data)
            session.add(chunk)
            models.append(chunk)
        await session.flush()
        return models

    async def list_document_chunks(
        self, session: AsyncSession, document_id: str
    ) -> list[ChunkModel]:
        """列出文档的所有块。"""
        stmt = (
            select(ChunkModel)
            .where(ChunkModel.document_id == document_id)
            .order_by(ChunkModel.sequence)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def mark_vector_indexed(
        self, session: AsyncSession, chunk_id: str, similarity_score: float | None = None
    ) -> ChunkModel:
        """标记块已索引到向量数据库。"""
        chunk = await self.get_by_id_required(session, chunk_id, "chunk_id")
        chunk.vector_indexed = True
        if similarity_score is not None:
            chunk.similarity_score = similarity_score
        await session.flush()
        return chunk


# 全局数据库服务实例
workflow_db = WorkflowDBService()
workflow_version_db = WorkflowVersionDBService()
workflow_run_db = WorkflowRunDBService()
node_run_db = NodeRunDBService()
workflow_approval_db = WorkflowApprovalDBService()
knowledge_base_db = KnowledgeBaseDBService()
document_db = DocumentDBService()
chunk_db = ChunkDBService()
