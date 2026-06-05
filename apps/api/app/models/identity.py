"""SQLAlchemy ORM 模型 - 用户与组织。

对应 domain/identity.py 中的领域模型，使用 MySQL 8.0。
 """

from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class UserModel(Base):
    """用户表。"""
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    memberships: Mapped[list["MembershipModel"]] = relationship(back_populates="user")


class OrganizationModel(Base):
    """组织表。"""
    __tablename__ = "organizations"

    org_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    teams: Mapped[list["TeamModel"]] = relationship(back_populates="organization")
    memberships: Mapped[list["MembershipModel"]] = relationship(back_populates="organization")


class TeamModel(Base):
    """群组表。"""
    __tablename__ = "teams"

    team_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    organization: Mapped["OrganizationModel"] = relationship(back_populates="teams")


class MembershipModel(Base):
    """成员关系表。"""
    __tablename__ = "memberships"
    __table_args__ = (
        # 联合唯一约束：同一组织中同一用户只能有一条成员关系
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    membership_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # owner/admin/member/viewer
    team_ids_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组存储 team_ids
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    organization: Mapped["OrganizationModel"] = relationship(back_populates="memberships")
    user: Mapped["UserModel"] = relationship(back_populates="memberships")


class AuditLogModel(Base):
    """审计日志表 - append-only。"""
    __tablename__ = "audit_logs"

    log_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RBACPolicyModel(Base):
    """RBAC 动态权限策略表。"""
    __tablename__ = "rbac_policies"

    policy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.org_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    permission: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed: Mapped[bool] = mapped_column(default=True)
    priority: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
