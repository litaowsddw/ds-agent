"""Harness policy bridge (RBAC role → sandbox/approval tier)."""

import pytest

from apps.api.app.domain.identity import OrganizationRole
from apps.api.app.services.harness_policy import (
    approval_mode_for_role,
    build_policy_for_role,
    sandbox_mode_for_role,
)
from packages.runtime.approval import ApprovalDecision, ApprovalMode
from packages.runtime.permissions import SandboxMode, ToolPermission


def test_owner_and_admin_get_danger_full_access() -> None:
    assert sandbox_mode_for_role(OrganizationRole.OWNER) is SandboxMode.DANGER_FULL_ACCESS
    assert sandbox_mode_for_role(OrganizationRole.ADMIN) is SandboxMode.DANGER_FULL_ACCESS
    assert approval_mode_for_role(OrganizationRole.OWNER) is ApprovalMode.ASK


def test_developer_gets_workspace_write_and_ask() -> None:
    assert sandbox_mode_for_role(OrganizationRole.DEVELOPER) is SandboxMode.WORKSPACE_WRITE
    assert approval_mode_for_role(OrganizationRole.DEVELOPER) is ApprovalMode.ASK


def test_viewer_is_read_only_and_never_approves() -> None:
    assert sandbox_mode_for_role(OrganizationRole.VIEWER) is SandboxMode.READ_ONLY
    policy = build_policy_for_role(OrganizationRole.VIEWER)
    assert policy.decide(ToolPermission.EXTERNAL) is ApprovalDecision.REJECTED
    assert policy.decide(ToolPermission.READ) is ApprovalDecision.APPROVED


def test_unknown_role_falls_back_to_least_privilege() -> None:
    assert sandbox_mode_for_role("bogus") is SandboxMode.READ_ONLY
    assert approval_mode_for_role("bogus") is ApprovalMode.NEVER
