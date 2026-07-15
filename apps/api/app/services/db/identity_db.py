"""用户与组织数据库服务。

替换 identity_store.py 的内存实现，使用 SQLAlchemy 异步操作 MySQL。
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import UserModel, OrganizationModel, TeamModel, MembershipModel, AuditLogModel
from app.services.db.base import BaseDBService


class UserDBService(BaseDBService[UserModel]):
    """用户数据库服务。"""

    def __init__(self) -> None:
        super().__init__(UserModel)

    async def get_by_email(self, session: AsyncSession, email: str) -> UserModel | None:
        """根据邮箱查找用户。"""
        stmt = select(UserModel).where(UserModel.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(
        self,
        session: AsyncSession,
        user_id: str,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> UserModel:
        """创建用户。"""
        user = UserModel(
            user_id=user_id,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
        )
        session.add(user)
        await session.flush()
        return user


class OrganizationDBService(BaseDBService[OrganizationModel]):
    """组织数据库服务。"""

    def __init__(self) -> None:
        super().__init__(OrganizationModel)

    async def create_org(
        self,
        session: AsyncSession,
        org_id: str,
        name: str,
        created_by: str,
    ) -> OrganizationModel:
        """创建组织。"""
        org = OrganizationModel(
            org_id=org_id,
            name=name,
            created_by=created_by,
        )
        session.add(org)
        await session.flush()
        return org

    async def list_user_orgs(self, session: AsyncSession, user_id: str) -> list[OrganizationModel]:
        """列出用户所属的组织。"""
        stmt = (
            select(OrganizationModel)
            .join(MembershipModel, MembershipModel.org_id == OrganizationModel.org_id)
            .where(MembershipModel.user_id == user_id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class TeamDBService(BaseDBService[TeamModel]):
    """群组数据库服务。"""

    def __init__(self) -> None:
        super().__init__(TeamModel)

    async def create_team(
        self,
        session: AsyncSession,
        team_id: str,
        org_id: str,
        name: str,
        created_by: str,
    ) -> TeamModel:
        """创建群组。"""
        team = TeamModel(
            team_id=team_id,
            org_id=org_id,
            name=name,
            created_by=created_by,
        )
        session.add(team)
        await session.flush()
        return team

    async def list_org_teams(self, session: AsyncSession, org_id: str) -> list[TeamModel]:
        """列出组织下的群组。"""
        stmt = select(TeamModel).where(TeamModel.org_id == org_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


class MembershipDBService(BaseDBService[MembershipModel]):
    """成员关系数据库服务。"""

    def __init__(self) -> None:
        super().__init__(MembershipModel)

    async def get_membership(
        self, session: AsyncSession, org_id: str, user_id: str
    ) -> MembershipModel | None:
        """获取用户在组织中的成员关系。"""
        stmt = select(MembershipModel).where(
            MembershipModel.org_id == org_id,
            MembershipModel.user_id == user_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def assert_org_access(
        self,
        session: AsyncSession,
        user_id: str,
        org_id: str,
        required_role: str | None = None,
    ) -> MembershipModel:
        """断言用户有权访问组织，否则抛出 ValueError。"""
        membership = await self.get_membership(session, org_id, user_id)
        if membership is None:
            raise ValueError("无权访问该组织")

        if required_role is not None:
            role_hierarchy = {"owner": 4, "admin": 3, "developer": 2, "member": 2, "viewer": 1}
            user_level = role_hierarchy.get(membership.role, 0)
            required_level = role_hierarchy.get(required_role, 0)
            if user_level < required_level:
                raise ValueError(f"权限不足，需要 {required_role} 角色")

        return membership

    async def add_member(
        self,
        session: AsyncSession,
        membership_id: str,
        org_id: str,
        user_id: str,
        role: str,
        team_ids: list[str] | None = None,
    ) -> MembershipModel:
        """添加组织成员。"""
        membership = MembershipModel(
            membership_id=membership_id,
            org_id=org_id,
            user_id=user_id,
            role=role,
            team_ids_json=json.dumps(team_ids or []),
        )
        session.add(membership)
        await session.flush()
        return membership

    async def list_user_memberships(
        self, session: AsyncSession, user_id: str
    ) -> list[MembershipModel]:
        """列出用户的所有成员关系。"""
        stmt = select(MembershipModel).where(MembershipModel.user_id == user_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_role(
        self,
        session: AsyncSession,
        membership_id: str,
        new_role: str,
    ) -> MembershipModel:
        """更新成员角色。"""
        membership = await self.get_by_id_required(session, membership_id)
        membership.role = new_role
        await session.flush()
        return membership


class AuditLogDBService(BaseDBService[AuditLogModel]):
    """审计日志数据库服务。"""

    def __init__(self) -> None:
        super().__init__(AuditLogModel)

    async def append_log(
        self,
        session: AsyncSession,
        log_id: str,
        org_id: str,
        actor_user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        detail: dict[str, Any] | None = None,
    ) -> AuditLogModel:
        """追加审计日志（append-only）。"""
        log = AuditLogModel(
            log_id=log_id,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=json.dumps(detail or {}),
        )
        session.add(log)
        await session.flush()
        return log

    async def list_org_logs(
        self,
        session: AsyncSession,
        org_id: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditLogModel], int]:
        """列出组织审计日志。"""
        return await self.list_paginated(
            session, offset=offset, limit=limit, org_id=org_id
        )


class RBACPolicyDBService(BaseDBService["RBACPolicyModel"]):
    """RBAC 动态权限策略数据库服务。"""

    def __init__(self) -> None:
        from app.models.identity import RBACPolicyModel
        super().__init__(RBACPolicyModel)

    async def list_org_policies(
        self, session: AsyncSession, org_id: str
    ) -> list["RBACPolicyModel"]:
        """列出组织所有动态策略。"""
        from app.models.identity import RBACPolicyModel
        stmt = select(RBACPolicyModel).where(RBACPolicyModel.org_id == org_id).order_by(RBACPolicyModel.priority.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create_policy(
        self,
        session: AsyncSession,
        policy_id: str,
        org_id: str,
        role: str,
        permission: str,
        allowed: bool = True,
        priority: int = 0,
        created_by: str = "",
    ) -> "RBACPolicyModel":
        """创建动态策略。"""
        from app.models.identity import RBACPolicyModel
        policy = RBACPolicyModel(
            policy_id=policy_id,
            org_id=org_id,
            role=role,
            permission=permission,
            allowed=allowed,
            priority=priority,
            created_by=created_by,
        )
        session.add(policy)
        await session.flush()
        return policy


# 全局数据库服务实例
user_db = UserDBService()
org_db = OrganizationDBService()
team_db = TeamDBService()
membership_db = MembershipDBService()
audit_log_db = AuditLogDBService()
rbac_policy_db = RBACPolicyDBService()
