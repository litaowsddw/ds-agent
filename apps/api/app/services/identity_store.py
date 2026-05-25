"""身份与租户内存存储。

MVP 阶段使用内存存储让权限模型和 API 可以立即运行。后续模块会把这里替换为
SQLAlchemy Repository，但外部服务接口尽量保持稳定。
"""

from apps.api.app.core.security import hash_password, verify_password
from apps.api.app.domain.identity import (
    AuditAction,
    AuditLog,
    Membership,
    Organization,
    OrganizationRole,
    Team,
    User,
    new_id,
)
from apps.api.app.services.rbac import Permission, RBACService
from apps.api.app.storage.local_state import local_state_store


class IdentityStore:
    """用户、组织、群组、成员和审计日志的 MVP 存储。"""

    def __init__(self) -> None:
        # users_by_id 保存用户实体，key 是 user_id。
        self.users_by_id: dict[str, User] = {}

        # users_by_email 保存 email 到 user_id 的索引，用于注册唯一性和登录。
        self.users_by_email: dict[str, str] = {}

        # organizations_by_id 保存组织实体，key 是 org_id。
        self.organizations_by_id: dict[str, Organization] = {}

        # teams_by_id 保存群组实体，key 是 team_id。
        self.teams_by_id: dict[str, Team] = {}

        # memberships_by_org_user 保存成员关系，key 是 org_id:user_id。
        self.memberships_by_org_user: dict[str, Membership] = {}

        # audit_logs 保存审计记录，MVP 阶段用列表保持写入顺序。
        self.audit_logs: list[AuditLog] = []

        # rbac_service 负责权限判断，存储层不直接硬编码角色权限。
        self.rbac_service = RBACService()
        self._load_state()

    def register_user(self, email: str, display_name: str, password: str) -> User:
        """注册用户。"""

        # normalized_email 是标准化后的邮箱，避免大小写造成重复账号。
        normalized_email = email.strip().lower()

        if normalized_email in self.users_by_email:
            raise ValueError("邮箱已注册")

        user = User(
            user_id=new_id("usr"),
            email=normalized_email,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
        )

        self.users_by_id[user.user_id] = user
        self.users_by_email[user.email] = user.user_id

        self._append_audit_log(
            org_id="",
            actor_user_id=user.user_id,
            action=AuditAction.USER_REGISTERED,
            target_type="user",
            target_id=user.user_id,
            detail={"email": user.email},
        )
        return user

    def authenticate_user(self, email: str, password: str) -> User:
        """校验用户邮箱和密码。"""

        # normalized_email 是标准化后的登录邮箱。
        normalized_email = email.strip().lower()

        # user_id 是邮箱索引找到的用户 ID。
        user_id = self.users_by_email.get(normalized_email)
        if user_id is None:
            raise ValueError("邮箱或密码错误")

        user = self.users_by_id[user_id]
        if not verify_password(password, user.password_hash):
            raise ValueError("邮箱或密码错误")

        return user

    def create_organization(self, creator_user_id: str, name: str) -> Organization:
        """创建组织，并让创建者成为 owner。"""

        self._require_user_exists(creator_user_id)

        organization = Organization(
            org_id=new_id("org"),
            name=name.strip(),
            created_by=creator_user_id,
        )
        self.organizations_by_id[organization.org_id] = organization

        membership = Membership(
            membership_id=new_id("mem"),
            org_id=organization.org_id,
            user_id=creator_user_id,
            role=OrganizationRole.OWNER,
        )
        self.memberships_by_org_user[self._membership_key(organization.org_id, creator_user_id)] = membership

        self._append_audit_log(
            org_id=organization.org_id,
            actor_user_id=creator_user_id,
            action=AuditAction.ORGANIZATION_CREATED,
            target_type="organization",
            target_id=organization.org_id,
            detail={"name": organization.name},
        )
        return organization

    def create_team(self, actor_user_id: str, org_id: str, name: str) -> Team:
        """在组织内创建群组。"""

        # actor_membership 是操作者在目标组织中的成员关系。
        actor_membership = self.get_membership(org_id=org_id, user_id=actor_user_id)
        self.rbac_service.require_permission(actor_membership, Permission.TEAM_CREATE)

        team = Team(
            team_id=new_id("team"),
            org_id=org_id,
            name=name.strip(),
            created_by=actor_user_id,
        )
        self.teams_by_id[team.team_id] = team

        self._append_audit_log(
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=AuditAction.TEAM_CREATED,
            target_type="team",
            target_id=team.team_id,
            detail={"name": team.name},
        )
        return team

    def add_member(
        self,
        actor_user_id: str,
        org_id: str,
        target_user_id: str,
        role: OrganizationRole,
        team_ids: list[str] | None = None,
    ) -> Membership:
        """向组织添加成员。"""

        actor_membership = self.get_membership(org_id=org_id, user_id=actor_user_id)
        self.rbac_service.require_permission(actor_membership, Permission.ORGANIZATION_MANAGE)
        self._require_user_exists(target_user_id)

        # final_team_ids 是成员加入的群组列表，空值表示只加入组织不加入具体群组。
        final_team_ids = team_ids or []
        for team_id in final_team_ids:
            self._require_team_in_org(team_id=team_id, org_id=org_id)

        membership = Membership(
            membership_id=new_id("mem"),
            org_id=org_id,
            user_id=target_user_id,
            role=role,
            team_ids=final_team_ids,
        )
        self.memberships_by_org_user[self._membership_key(org_id, target_user_id)] = membership

        self._append_audit_log(
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=AuditAction.MEMBER_JOINED,
            target_type="membership",
            target_id=membership.membership_id,
            detail={"target_user_id": target_user_id, "role": role.value},
        )
        return membership

    def list_organizations_for_user(self, user_id: str) -> list[Organization]:
        """列出用户所属组织。"""

        self._require_user_exists(user_id)

        # org_ids 是用户拥有 membership 的组织 ID 列表。
        org_ids = [
            membership.org_id
            for membership in self.memberships_by_org_user.values()
            if membership.user_id == user_id
        ]
        return [self.organizations_by_id[org_id] for org_id in org_ids]

    def list_teams(self, actor_user_id: str, org_id: str) -> list[Team]:
        """列出组织内群组。"""

        actor_membership = self.get_membership(org_id=org_id, user_id=actor_user_id)
        self.rbac_service.require_permission(actor_membership, Permission.TEAM_READ)

        return [team for team in self.teams_by_id.values() if team.org_id == org_id]

    def get_membership(self, org_id: str, user_id: str) -> Membership | None:
        """获取用户在组织内的成员关系。"""

        return self.memberships_by_org_user.get(self._membership_key(org_id, user_id))

    def assert_org_access(self, user_id: str, org_id: str, permission: Permission) -> None:
        """校验用户是否拥有组织内指定权限。"""

        membership = self.get_membership(org_id=org_id, user_id=user_id)
        self.rbac_service.require_permission(membership, permission)

        self._append_audit_log(
            org_id=org_id,
            actor_user_id=user_id,
            action=AuditAction.PERMISSION_CHECKED,
            target_type="organization",
            target_id=org_id,
            detail={"permission": permission.value},
        )

    def list_audit_logs(self, actor_user_id: str, org_id: str) -> list[AuditLog]:
        """列出组织审计日志。"""

        actor_membership = self.get_membership(org_id=org_id, user_id=actor_user_id)
        self.rbac_service.require_permission(actor_membership, Permission.AUDIT_READ)

        return [audit_log for audit_log in self.audit_logs if audit_log.org_id == org_id]

    def _append_audit_log(
        self,
        org_id: str,
        actor_user_id: str,
        action: AuditAction,
        target_type: str,
        target_id: str,
        detail: dict[str, object],
    ) -> None:
        """追加一条审计日志。"""

        audit_log = AuditLog(
            audit_id=new_id("aud"),
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
        self.audit_logs.append(audit_log)
        self._save_state()

    def _load_state(self) -> None:
        """从本地状态文件恢复身份与组织数据。"""

        state = local_state_store.load_bucket("identity", {})
        if not isinstance(state, dict):
            return
        self.users_by_id = state.get("users_by_id", self.users_by_id)
        self.users_by_email = state.get("users_by_email", self.users_by_email)
        self.organizations_by_id = state.get("organizations_by_id", self.organizations_by_id)
        self.teams_by_id = state.get("teams_by_id", self.teams_by_id)
        self.memberships_by_org_user = state.get(
            "memberships_by_org_user",
            self.memberships_by_org_user,
        )
        self.audit_logs = state.get("audit_logs", self.audit_logs)

    def _save_state(self) -> None:
        """把身份与组织数据保存到本地状态文件。"""

        local_state_store.save_bucket(
            "identity",
            {
                "users_by_id": self.users_by_id,
                "users_by_email": self.users_by_email,
                "organizations_by_id": self.organizations_by_id,
                "teams_by_id": self.teams_by_id,
                "memberships_by_org_user": self.memberships_by_org_user,
                "audit_logs": self.audit_logs,
            },
        )

    def _require_user_exists(self, user_id: str) -> None:
        """要求用户必须存在。"""

        if user_id not in self.users_by_id:
            raise ValueError("用户不存在")

    def _require_team_in_org(self, team_id: str, org_id: str) -> None:
        """要求群组属于指定组织。"""

        team = self.teams_by_id.get(team_id)
        if team is None or team.org_id != org_id:
            raise ValueError("群组不存在或不属于该组织")

    def _membership_key(self, org_id: str, user_id: str) -> str:
        """生成成员关系索引键。"""

        return f"{org_id}:{user_id}"


# identity_store 是 MVP 阶段的进程内身份存储。
identity_store = IdentityStore()

