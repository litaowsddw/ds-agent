"""SQLAlchemy ORM 模型 - Workflow、WorkflowRun、Knowledge。"""

from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class WorkflowModel(Base):
    """Workflow 表。"""
    __tablename__ = "workflows"

    workflow_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.agent_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    draft_definition: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    published_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    versions: Mapped[list["WorkflowVersionModel"]] = relationship(back_populates="workflow")
    runs: Mapped[list["WorkflowRunModel"]] = relationship(back_populates="workflow")


class WorkflowVersionModel(Base):
    """Workflow 版本表 - 发布版本不可变。"""
    __tablename__ = "workflow_versions"

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(64), ForeignKey("workflows.workflow_id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)  # JSON - 不可变快照
    # 发布说明与快照一起写入，供团队审计、排障与回滚决策使用。
    release_note: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    workflow: Mapped["WorkflowModel"] = relationship(back_populates="versions")


class WorkflowRunModel(Base):
    """Workflow 运行表。"""
    __tablename__ = "workflow_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(64), ForeignKey("workflows.workflow_id"), nullable=False, index=True)
    version_id: Mapped[str] = mapped_column(String(64), ForeignKey("workflow_versions.version_id"), nullable=False)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Approval can leave a run in ``awaiting_manual_resume``; keep enough
    # room for explicit lifecycle states instead of truncating them in MySQL.
    status: Mapped[str] = mapped_column(String(32), default="pending")
    input_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    output_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    workflow: Mapped["WorkflowModel"] = relationship(back_populates="runs")
    node_runs: Mapped[list["NodeRunModel"]] = relationship(back_populates="run")


class NodeRunModel(Base):
    """节点运行日志表。"""
    __tablename__ = "node_runs"

    node_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("workflow_runs.run_id"), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    input_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    output_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    error_message: Mapped[str] = mapped_column(Text, default="")
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 关系
    run: Mapped["WorkflowRunModel"] = relationship(back_populates="node_runs")


class WorkflowApprovalRequestModel(Base):
    """Durable approval gate for a high-risk Workflow MCP tool invocation.

    ``arguments_encrypted`` is deliberately never returned by an API.  The
    operator sees ``arguments_redacted`` while the reviewed execution service
    can decrypt the exact, already-resolved invocation only after approval.
    """

    __tablename__ = "workflow_approval_requests"

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.run_id"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_id: Mapped[str] = mapped_column(String(64), nullable=False)
    server_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    arguments_redacted: Mapped[str] = mapped_column(Text, default="{}")
    arguments_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    execution_node_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeBaseModel(Base):
    """知识库表。"""
    __tablename__ = "knowledge_bases"

    kb_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    embedding_model: Mapped[str] = mapped_column(String(128), default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    documents: Mapped[list["DocumentModel"]] = relationship(back_populates="knowledge_base")


class DocumentModel(Base):
    """文档表。"""
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_bases.kb_id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/indexing/indexed/failed
    chunk_size: Mapped[int] = mapped_column(Integer, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=100)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    knowledge_base: Mapped["KnowledgeBaseModel"] = relationship(back_populates="documents")
    chunks: Mapped[list["ChunkModel"]] = relationship(back_populates="document")


class ChunkModel(Base):
    """文档块表。"""
    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.document_id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str] = mapped_column(String(128), default="")
    vector_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 关系
    document: Mapped["DocumentModel"] = relationship(back_populates="chunks")
