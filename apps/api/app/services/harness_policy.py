"""Harness policy bridge — maps RBAC roles to harness sandbox/approval tiers.

The runtime harness (``packages.runtime.permissions`` / ``approval``) is
deployment-agnostic.  This module binds it to AgentFlow's RBAC roles the way
DSH's permission-presets bind a sandbox to a caller: OWNER/ADMIN get
danger-full-access with approval, DEVELOPER gets workspace-write, and VIEWER is
read-only with approval disabled.
"""

from __future__ import annotations

from apps.api.app.domain.identity import OrganizationRole
from packages.runtime.approval import ApprovalMode, ApprovalPolicy
from packages.runtime.permissions import SandboxMode

_ROLE_SANDBOX_MODE: dict[OrganizationRole, SandboxMode] = {
    OrganizationRole.OWNER: SandboxMode.DANGER_FULL_ACCESS,
    OrganizationRole.ADMIN: SandboxMode.DANGER_FULL_ACCESS,
    OrganizationRole.DEVELOPER: SandboxMode.WORKSPACE_WRITE,
    OrganizationRole.VIEWER: SandboxMode.READ_ONLY,
}

_ROLE_APPROVAL_MODE: dict[OrganizationRole, ApprovalMode] = {
    OrganizationRole.OWNER: ApprovalMode.ASK,
    OrganizationRole.ADMIN: ApprovalMode.ASK,
    OrganizationRole.DEVELOPER: ApprovalMode.ASK,
    OrganizationRole.VIEWER: ApprovalMode.NEVER,
}


def _coerce_role(role: OrganizationRole | str) -> OrganizationRole | None:
    if isinstance(role, OrganizationRole):
        return role
    try:
        return OrganizationRole(str(role))
    except ValueError:
        return None


def sandbox_mode_for_role(role: OrganizationRole | str) -> SandboxMode:
    """The sandbox tier granted to a membership role (read-only fallback)."""

    return _ROLE_SANDBOX_MODE.get(_coerce_role(role), SandboxMode.READ_ONLY)


def approval_mode_for_role(role: OrganizationRole | str) -> ApprovalMode:
    """The approval mode granted to a membership role (never fallback)."""

    return _ROLE_APPROVAL_MODE.get(_coerce_role(role), ApprovalMode.NEVER)


def build_policy_for_role(role: OrganizationRole | str) -> ApprovalPolicy:
    """Build the ApprovalPolicy for a membership role."""

    return ApprovalPolicy(approval_mode_for_role(role))
