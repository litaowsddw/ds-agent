"""Approval policy — models DeepSeek Harness ``dsh-user-approval``.

The approval gate sits above the sandbox tiers: actions inside the workspace
(READ / WRITE) proceed, while EXTERNAL actions (shell and other irreversible
work) require user approval.  In ``ask`` mode the gate yields ``pending`` (the
runtime pauses for the user); in ``never`` mode it rejects automatically.  This
is the decision model the runtime wires to its RBAC/approval channel.
"""

from __future__ import annotations

from enum import StrEnum

from packages.runtime.permissions import ToolPermission


class ApprovalMode(StrEnum):
    ASK = "ask"
    NEVER = "never"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"


class ApprovalPolicy:
    """Decide whether a tool permission tier may proceed under the active mode."""

    def __init__(self, mode: ApprovalMode | str = ApprovalMode.ASK) -> None:
        self.mode = ApprovalMode(str(mode))

    def decide(self, permission: ToolPermission | str) -> ApprovalDecision:
        permission = ToolPermission(str(permission))
        if permission is not ToolPermission.EXTERNAL:
            return ApprovalDecision.APPROVED
        if self.mode is ApprovalMode.NEVER:
            return ApprovalDecision.REJECTED
        return ApprovalDecision.PENDING
