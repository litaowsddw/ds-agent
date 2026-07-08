"""SQLAlchemy ORM 模型 - Agent 与 Workspace。

对应 domain/agent.py，扩展了 AgentKind、model_provider 等新字段。
 """

from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AgentModel(Base):
    """Agent 表。"""
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.team_id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # 新增字段 - 对应 Supervisor/SubAgent 架构
    kind: Mapped[str] = mapped_column(String(32), default="USER_SUB")  # SUPERVISOR/USER_SUB/SYSTEM_SKILL/SYSTEM_RAG/SYSTEM_TOOL
    workspace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    temperature: Mapped[float | None] = mapped_column(nullable=True, default=0.0)
    max_tokens: Mapped[int | None] = mapped_column(nullable=True)
    default_workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # A2A Agent Card URL
    a2a_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    agent_card_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    workspace: Mapped["AgentWorkspaceModel | None"] = relationship(back_populates="agent", uselist=False)


class AgentWorkspaceModel(Base):
    """Agent Workspace 表 - 与 Agent 1:1 关系。"""
    __tablename__ = "agent_workspaces"

    workspace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.agent_id"), unique=True, nullable=False)
    agents_md: Mapped[str] = mapped_column(Text, default="")
    soul_md: Mapped[str] = mapped_column(Text, default="")
    tools_md: Mapped[str] = mapped_column(Text, default="")
    memory_md: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    agent: Mapped["AgentModel"] = relationship(back_populates="workspace")
