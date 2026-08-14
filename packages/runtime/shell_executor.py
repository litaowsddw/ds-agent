"""Local shell executor — models DeepSeek Harness ``dsh-bash-local``/``dsh-pwsh-local``.

Runs a shell command in a subprocess confined to a working directory with a
timeout.  It is the first-level boundary for the ``shell`` tool; deeper OS
isolation (read-only filesystem, network off) belongs to the deployment's
sandbox, which may wrap or replace this executor.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


class LocalShellExecutor:
    """Execute shell commands via ``subprocess`` with cwd confinement and timeout."""

    def __init__(self, *, cwd: str | Path | None = None, timeout_seconds: float = 30.0) -> None:
        self.cwd = str(cwd) if cwd is not None else None
        self.timeout_seconds = timeout_seconds

    async def __call__(self, command: str) -> dict[str, object]:
        return await asyncio.to_thread(self._run_sync, command)

    def _run_sync(self, command: str) -> dict[str, object]:
        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=self.timeout_seconds,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            return {"output": output, "exit_code": completed.returncode}
        except subprocess.TimeoutExpired:
            return {
                "output": f"command timed out after {self.timeout_seconds}s",
                "exit_code": 124,
            }
