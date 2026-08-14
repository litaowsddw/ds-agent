"""Approval policy."""

import pytest

from packages.runtime.approval import ApprovalDecision, ApprovalMode, ApprovalPolicy
from packages.runtime.permissions import ToolPermission


def test_ask_mode_pends_external_and_approves_internal() -> None:
    policy = ApprovalPolicy(ApprovalMode.ASK)

    assert policy.decide(ToolPermission.READ) is ApprovalDecision.APPROVED
    assert policy.decide(ToolPermission.WRITE) is ApprovalDecision.APPROVED
    assert policy.decide(ToolPermission.EXTERNAL) is ApprovalDecision.PENDING


def test_never_mode_rejects_external_only() -> None:
    policy = ApprovalPolicy(ApprovalMode.NEVER)

    assert policy.decide(ToolPermission.EXTERNAL) is ApprovalDecision.REJECTED
    assert policy.decide(ToolPermission.WRITE) is ApprovalDecision.APPROVED
    assert policy.decide(ToolPermission.READ) is ApprovalDecision.APPROVED


def test_approval_policy_accepts_string_mode() -> None:
    policy = ApprovalPolicy("never")
    assert policy.mode is ApprovalMode.NEVER
