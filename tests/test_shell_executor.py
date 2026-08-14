"""Local shell executor."""

import pytest

from packages.runtime.shell_executor import LocalShellExecutor


@pytest.mark.asyncio
async def test_local_shell_executor_runs_command() -> None:
    executor = LocalShellExecutor(timeout_seconds=10)
    result = await executor("echo hello")

    assert result["exit_code"] == 0
    assert "hello" in result["output"]


@pytest.mark.asyncio
async def test_local_shell_executor_reports_nonzero_exit() -> None:
    executor = LocalShellExecutor(timeout_seconds=10)
    result = await executor("exit 3")

    assert result["exit_code"] == 3


@pytest.mark.asyncio
async def test_local_shell_executor_confines_to_working_directory(tmp_path) -> None:
    (tmp_path / "marker.txt").write_text("hi", encoding="utf-8")
    executor = LocalShellExecutor(cwd=str(tmp_path), timeout_seconds=10)

    # `dir`/`ls` differ by platform; use a python one-liner that is portable.
    result = await executor("python -c \"import os; print(os.listdir('.'))\"")
    assert "marker.txt" in result["output"]
