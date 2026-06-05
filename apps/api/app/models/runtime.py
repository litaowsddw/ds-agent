"""SQLAlchemy ORM 模型 - Skill、MCP、Memory、Knowledge 等运行时资源。"""

from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SkillModel(Base):
    """Skill 表 - 对应 SKILL.md 文件。"""
    __tablename__ = "skills"

    skill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.team_id"), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("agents.agent_id"), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)  # bundled/organization/team/agent
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # SKILL.md 文件路径
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentSkillPolicyModel(Base):
    """Agent Skill 授权策略表。"""
    __tablename__ = "agent_skill_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.agent_id"), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(64), ForeignKey("skills.skill_id"), nullable=False, index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)


class MCPServerModel(Base):
    """MCP Server 表。"""
    __tablename__ = "mcp_servers"

    server_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), default="http")
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MCPToolModel(Base):
    """MCP Tool 表。"""
    __tablename__ = "mcp_tools"

    tool_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    server_id: Mapped[str] = mapped_column(String(64), ForeignKey("mcp_servers.server_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema: Mapped[str] = mapped_column(Text, default="{}")
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentMCPPolicyModel(Base):
    """Agent MCP 授权策略表。"""
    __tablename__ = "agent_mcp_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.agent_id"), nullable=False, index=True)
    server_id: Mapped[str] = mapped_column(String(64), ForeignKey("mcp_servers.server_id"), nullable=False, index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)


class MemoryModel(Base):
    """Memory 记忆表。"""
    __tablename__ = "memories"

    memory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.agent_id"), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str] = mapped_column(String(64), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelProviderModel(Base):
    """模型供应商配置表。"""
    __tablename__ = "model_providers"

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    api_key_masked: Mapped[str] = mapped_column(String(64), default="")
    models_json: Mapped[str] = mapped_column(Text, default="[]")
    default_model: Mapped[str] = mapped_column(String(128), default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BackgroundAgentModel(Base):
    """后台 Agent 配置表。"""
    __tablename__ = "background_agents"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False)  # memory/mcp_health/workflow_monitor/queue_governor
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    status: Mapped[str] = mapped_column(String(16), default="idle")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SkillEvaluationModel(Base):
    """Skill 使用评价表。"""
    __tablename__ = "skill_evaluations"

    evaluation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.agent_id"), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(64), ForeignKey("skills.skill_id"), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("sessions.session_id"), nullable=True)
    user_input: Mapped[str] = mapped_column(Text, default="")
    assistant_output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/evaluated/applied/rejected
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    improvement_suggestion: Mapped[str] = mapped_column(Text, default="")
    proposed_skill_patch: Mapped[str] = mapped_column(Text, default="")
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
