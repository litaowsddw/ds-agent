"""Tool sandbox/permission model — models DeepSeek Harness sandbox tiers.

Three sandbox modes gate which tools an agent may call, mirroring DSH's
``read-only`` / ``workspace-write`` / ``danger-full-access`` tiers:

- ``READ_ONLY``          — non-mutating reads only.
- ``WORKSPACE_WRITE``    — plus mutations of the agent's own workspace/state.
- ``DANGER_FULL_ACCESS`` — plus external/irreversible actions (shell, network).

The per-tool permission map lives here in one place; the tool registry consults
it when filtering the catalog against the granted mode.
"""

from __future__ import annotations

from enum import StrEnum


class SandboxMode(StrEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class ToolPermission(StrEnum):
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"


_MODE_RANK = {
    SandboxMode.READ_ONLY: 0,
    SandboxMode.WORKSPACE_WRITE: 1,
    SandboxMode.DANGER_FULL_ACCESS: 2,
}
_PERMISSION_RANK = {
    ToolPermission.READ: 0,
    ToolPermission.WRITE: 1,
    ToolPermission.EXTERNAL: 2,
}

# Tool name → required permission. Anything unlisted defaults to READ.
_TOOL_PERMISSIONS: dict[str, ToolPermission] = {
    "todo_write": ToolPermission.WRITE,
    "create_goal": ToolPermission.WRITE,
    "update_goal": ToolPermission.WRITE,
    "exit_plan_mode": ToolPermission.WRITE,
    "write_file": ToolPermission.WRITE,
    "edit_file": ToolPermission.WRITE,
    "skill_create": ToolPermission.WRITE,
    "spawn_subagent": ToolPermission.WRITE,
    "subagent_fork": ToolPermission.WRITE,
    "kill_job": ToolPermission.WRITE,
    "ralph": ToolPermission.WRITE,
    "workflow": ToolPermission.WRITE,
    "shell": ToolPermission.EXTERNAL,
}


def permission_for(tool_name: str) -> ToolPermission:
    """Return the permission tier a tool requires (default READ)."""

    return _TOOL_PERMISSIONS.get(str(tool_name), ToolPermission.READ)


def allows(mode: SandboxMode | str, permission: ToolPermission | str) -> bool:
    """Whether a granted sandbox mode permits a tool permission tier."""

    mode = SandboxMode(str(mode))
    permission = ToolPermission(str(permission))
    return _PERMISSION_RANK[permission] <= _MODE_RANK[mode]
