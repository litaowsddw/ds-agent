"""Sandbox permission model and its registry integration."""

import json

import pytest

from packages.runtime.permissions import (
    SandboxMode,
    ToolPermission,
    allows,
    permission_for,
)
from packages.runtime.tools.registry import build_system_tools
from packages.runtime.tools.shell_tool import ShellTool


def test_permission_for_defaults_to_read_and_maps_writes() -> None:
    assert permission_for("read_file") is ToolPermission.READ
    assert permission_for("write_file") is ToolPermission.WRITE
    assert permission_for("edit_file") is ToolPermission.WRITE
    assert permission_for("shell") is ToolPermission.EXTERNAL
    assert permission_for("some_unknown_tool") is ToolPermission.READ


def test_allows_ranks_modes() -> None:
    assert allows(SandboxMode.READ_ONLY, ToolPermission.READ)
    assert not allows(SandboxMode.READ_ONLY, ToolPermission.WRITE)
    assert not allows(SandboxMode.READ_ONLY, ToolPermission.EXTERNAL)

    assert allows(SandboxMode.WORKSPACE_WRITE, ToolPermission.WRITE)
    assert not allows(SandboxMode.WORKSPACE_WRITE, ToolPermission.EXTERNAL)

    assert allows(SandboxMode.DANGER_FULL_ACCESS, ToolPermission.EXTERNAL)


def test_registry_filters_catalog_by_sandbox_mode() -> None:
    fs = object()  # placeholder; the filter only inspects tool names

    read_only = build_system_tools(
        org_id="o",
        agent_id="a",
        filesystem=fs,
        todo_store=lambda todos: todos,
        shell_executor=lambda **kwargs: {},
        sandbox_mode=SandboxMode.READ_ONLY,
    )
    names = {tool.name for tool in read_only}
    assert "read_file" in names
    assert "glob_files" in names
    assert "grep_files" in names
    assert "write_file" not in names
    assert "todo_write" not in names
    assert "shell" not in names

    workspace_write = build_system_tools(
        org_id="o",
        agent_id="a",
        filesystem=fs,
        todo_store=lambda todos: todos,
        shell_executor=lambda **kwargs: {},
        sandbox_mode=SandboxMode.WORKSPACE_WRITE,
    )
    names = {tool.name for tool in workspace_write}
    assert "write_file" in names
    assert "todo_write" in names
    assert "shell" not in names

    full = build_system_tools(
        org_id="o",
        agent_id="a",
        filesystem=fs,
        shell_executor=lambda **kwargs: {},
        sandbox_mode=SandboxMode.DANGER_FULL_ACCESS,
    )
    assert "shell" in {tool.name for tool in full}


@pytest.mark.asyncio
async def test_shell_tool_uses_executor_and_fails_honestly() -> None:
    async def executor(command: str) -> dict[str, object]:
        return {"output": "ok", "exit_code": 0}

    tool = ShellTool(shell_executor=executor)
    result = json.loads(await tool.ainvoke({"command": "echo hi"}))
    assert result == {"output": "ok", "exit_code": 0}

    assert json.loads(await ShellTool().ainvoke({"command": "x"})) == {
        "error": "Shell executor is not configured"
    }
