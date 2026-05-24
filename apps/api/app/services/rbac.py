"""RBAC 权限服务。

该模块集中维护角色到动作的授权关系。后续所有资源服务都应该调用这里，
避免在不同 API 路由里散落权限判断。
"""

from enum import StrEnum

from apps.api.app.domain.identity import Membership, OrganizationRole


class Permission(StrEnum):
    """系统权限枚举。"""

    ORGANIZATION_READ = "organization:read"
    ORGANIZATION_MANAGE = "organization:manage"
    TEAM_CREATE = "team:create"
    TEAM_READ = "team:read"
    TEAM_MANAGE = "team:manage"
    AGENT_CREATE = "agent:create"
    WORKFLOW_CREATE = "workflow:create"
    AUDIT_READ = "audit:read"


# ROLE_PERMISSIONS 是角色到权限集合的映射。
ROLE_PERMISSIONS: dict[OrganizationRole, set[Permission]] = {
    OrganizationRole.OWNER: set(Permission),
    OrganizationRole.ADMIN: {
        Permission.ORGANIZATION_READ,
        Permission.ORGANIZATION_MANAGE,
        Permission.TEAM_CREATE,
        Permission.TEAM_READ,
        Permission.TEAM_MANAGE,
        Permission.AGENT_CREATE,
        Permission.WORKFLOW_CREATE,
        Permission.AUDIT_READ,
    },
    OrganizationRole.DEVELOPER: {
        Permission.ORGANIZATION_READ,
        Permission.TEAM_READ,
        Permission.AGENT_CREATE,
        Permission.WORKFLOW_CREATE,
    },
    OrganizationRole.VIEWER: {
        Permission.ORGANIZATION_READ,
        Permission.TEAM_READ,
    },
}


class RBACService:
    """基于组织成员角色判断权限。"""

    def has_permission(self, membership: Membership | None, permission: Permission) -> bool:
        """判断成员是否拥有指定权限。"""

        # missing_membership 表示用户不属于该组织，因此没有任何组织权限。
        missing_membership = membership is None
        if missing_membership:
            return False

        # allowed_permissions 是当前角色拥有的权限集合。
        allowed_permissions = ROLE_PERMISSIONS.get(membership.role, set())
        return permission in allowed_permissions

    def require_permission(self, membership: Membership | None, permission: Permission) -> None:
        """要求成员必须拥有指定权限，否则抛出权限错误。"""

        if not self.has_permission(membership, permission):
            raise PermissionError(f"缺少权限：{permission.value}")

