"""SQLAlchemy ORM 模型 - Session 与消息。"""

from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SessionModel(Base):
    """Agent 会话表。"""
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.agent_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    queue_mode: Mapped[str] = mapped_column(String(16), default="queue")  # queue / collect
    status: Mapped[str] = mapped_column(String(16), default="idle")  # idle / running / closed
    compact_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    messages: Mapped[list["SessionMessageModel"]] = relationship(back_populates="session", order_by="SessionMessageModel.sequence")


class SessionMessageModel(Base):
    """会话消息表 - append-only。"""
    __tablename__ = "session_messages"

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.session_id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user/assistant/system/tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, default=0)
    compacted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    session: Mapped["SessionModel"] = relationship(back_populates="messages")
