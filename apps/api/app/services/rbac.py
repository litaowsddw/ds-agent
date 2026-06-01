"""RBAC 权限服务（数据库版本）。

Sprint 4 升级：
- 资源级细粒度权限（从 8 个扩展到 20+）
- 数据库策略表支持（RBACPolicyModel）
- 动态策略覆盖（组织可自定义权限规则）
"""

from enum import StrEnum
from dataclasses import dataclass, field
from typing import Any

from apps.api.app.domain.identity import Membership, OrganizationRole


class Permission(StrEnum):
    """系统权限枚举。

    权限命名规范：resource:action
    - organization:* — 组织级管理
    - team:* — 群组管理
    - agent:* — Agent 管理
    - workflow:* — 工作流管理
    - skill:* — Skill 管理
    - mcp:* — MCP Server 管理
    - memory:* — Memory 管理
    - knowledge:* — 知识库管理
    - session:* — Session 管理
    - gateway:* — Gateway/LLM 管理
    - audit:* — 审计日志
    - evolver:* — Skill Evolver 管理
    """

    # ── 组织 ──
    ORGANIZATION_READ = "organization:read"
    ORGANIZATION_MANAGE = "organization:manage"
    ORGANIZATION_BILLING = "organization:billing"

    # ── 群组 ──
    TEAM_CREATE = "team:create"
    TEAM_READ = "team:read"
    TEAM_MANAGE = "team:manage"

    # ── Agent ──
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_CHAT = "agent:chat"

    # ── 工作流 ──
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_UPDATE = "workflow:update"
    WORKFLOW_DELETE = "workflow:delete"
    WORKFLOW_RUN = "workflow:run"

    # ── Skill ──
    SKILL_CREATE = "skill:create"
    SKILL_READ = "skill:read"
    SKILL_MANAGE = "skill:manage"

    # ── MCP ──
    MCP_CREATE = "mcp:create"
    MCP_READ = "mcp:read"
    MCP_MANAGE = "mcp:manage"

    # ── Memory ──
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"

    # ── Knowledge ──
    KNOWLEDGE_CREATE = "knowledge:create"
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_MANAGE = "knowledge:manage"

    # ── Session ──
    SESSION_READ = "session:read"
    SESSION_WRITE = "session:write"

    # ── Gateway ──
    GATEWAY_READ = "gateway:read"
    GATEWAY_MANAGE = "gateway:manage"

    # ── 审计 ──
    AUDIT_READ = "audit:read"

    # ── Evolver ──
    EVOLVER_TRIGGER = "evolver:trigger"
    EVOLVER_APPROVE = "evolver:approve"
    EVOLVER_READ = "evolver:read"


# ROLE_PERMISSIONS 是角色到权限集合的映射。
ROLE_PERMISSIONS: dict[OrganizationRole, set[Permission]] = {
    OrganizationRole.OWNER: set(Permission),
    OrganizationRole.ADMIN: {
        # 组织
        Permission.ORGANIZATION_READ,
        Permission.ORGANIZATION_MANAGE,
        # 群组
        Permission.TEAM_CREATE,
        Permission.TEAM_READ,
        Permission.TEAM_MANAGE,
        # Agent
        Permission.AGENT_CREATE,
        Permission.AGENT_READ,
        Permission.AGENT_UPDATE,
        Permission.AGENT_DELETE,
        Permission.AGENT_CHAT,
        # 工作流
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_UPDATE,
        Permission.WORKFLOW_DELETE,
        Permission.WORKFLOW_RUN,
        # Skill
        Permission.SKILL_CREATE,
        Permission.SKILL_READ,
        Permission.SKILL_MANAGE,
        # MCP
        Permission.MCP_CREATE,
        Permission.MCP_READ,
        Permission.MCP_MANAGE,
        # Memory
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        # Knowledge
        Permission.KNOWLEDGE_CREATE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_MANAGE,
        # Session
        Permission.SESSION_READ,
        Permission.SESSION_WRITE,
        # Gateway
        Permission.GATEWAY_READ,
        Permission.GATEWAY_MANAGE,
        # 审计
        Permission.AUDIT_READ,
        # Evolver
        Permission.EVOLVER_TRIGGER,
        Permission.EVOLVER_APPROVE,
        Permission.EVOLVER_READ,
    },
    OrganizationRole.DEVELOPER: {
        Permission.ORGANIZATION_READ,
        Permission.TEAM_READ,
        Permission.AGENT_CREATE,
        Permission.AGENT_READ,
        Permission.AGENT_UPDATE,
        Permission.AGENT_CHAT,
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_UPDATE,
        Permission.WORKFLOW_RUN,
        Permission.SKILL_CREATE,
        Permission.SKILL_READ,
        Permission.MCP_READ,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.KNOWLEDGE_CREATE,
        Permission.KNOWLEDGE_READ,
        Permission.SESSION_READ,
        Permission.SESSION_WRITE,
        Permission.GATEWAY_READ,
        Permission.EVOLVER_TRIGGER,
        Permission.EVOLVER_READ,
    },
    OrganizationRole.VIEWER: {
        Permission.ORGANIZATION_READ,
        Permission.TEAM_READ,
        Permission.AGENT_READ,
        Permission.WORKFLOW_READ,
        Permission.SKILL_READ,
        Permission.MCP_READ,
        Permission.KNOWLEDGE_READ,
        Permission.SESSION_READ,
        Permission.EVOLVER_READ,
    },
}


@dataclass(slots=True)
class RBACPolicy:
    """动态权限策略。

    支持组织级自定义权限覆盖，例如：
    - 某组织禁止 developer 删除 Agent
    - 某组织允许 viewer 触发 Evolver
    """

    policy_id: str
    org_id: str
    role: str
    permission: str
    allowed: bool
    created_by: str = ""
    priority: int = 0  # 优先级，数值越大优先级越高


class RBACService:
    """基于组织成员角色判断权限。

    Sprint 4 升级：
    - 支持动态策略覆盖
    - 支持批量权限检查
    """

    def __init__(self, dynamic_policies: list[RBACPolicy] | None = None) -> None:
        # dynamic_policies 是组织级自定义策略。
        self._policies: dict[str, list[RBACPolicy]] = {}
        if dynamic_policies:
            for p in dynamic_policies:
                self._policies.setdefault(p.org_id, []).append(p)

    def has_permission(self, membership: Membership | None, permission: Permission) -> bool:
        """判断成员是否拥有指定权限。

        检查流程：
        1. 检查动态策略（优先级高）
        2. 检查角色默认权限
        """
        if membership is None:
            return False

        # 1. 动态策略检查
        org_policies = self._policies.get(membership.org_id, [])
        matching = [
            p for p in org_policies
            if p.role == membership.role.value and p.permission == permission.value
        ]
        if matching:
            # 按优先级排序，取最高优先级的策略
            best = max(matching, key=lambda p: p.priority)
            return best.allowed

        # 2. 角色默认权限
        allowed_permissions = ROLE_PERMISSIONS.get(membership.role, set())
        return permission in allowed_permissions

    def require_permission(self, membership: Membership | None, permission: Permission) -> None:
        """要求成员必须拥有指定权限，否则抛出权限错误。"""
        if not self.has_permission(membership, permission):
            raise PermissionError(f"缺少权限：{permission.value}")

    def get_permissions(self, membership: Membership | None) -> set[Permission]:
        """获取成员所有权限集合。"""
        if membership is None:
            return set()

        # 角色默认权限
        base_permissions = ROLE_PERMISSIONS.get(membership.role, set())

        # 动态策略增减
        org_policies = self._policies.get(membership.org_id, [])
        role_policies = [p for p in org_policies if p.role == membership.role.value]

        result = set(base_permissions)
        for policy in role_policies:
            try:
                perm = Permission(policy.permission)
                if policy.allowed:
                    result.add(perm)
                else:
                    result.discard(perm)
            except ValueError:
                pass

        return result

    def add_policy(self, policy: RBACPolicy) -> None:
        """添加动态策略。"""
        self._policies.setdefault(policy.org_id, []).append(policy)

    def remove_policy(self, org_id: str, policy_id: str) -> None:
        """移除动态策略。"""
        if org_id in self._policies:
            self._policies[org_id] = [
                p for p in self._policies[org_id] if p.policy_id != policy_id
            ]


# 全局 RBAC 服务实例
rbac_service = RBACService()
