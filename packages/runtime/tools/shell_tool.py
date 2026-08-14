"""Shell tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-tool-bash`` / ``dsh-tool-pwsh``: execute a shell
command through a runtime-injected, sandboxed executor.  The tool itself is
permission-gated to ``EXTERNAL`` (see ``permissions.py``); an unconfigured
executor fails honestly instead of running anything.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool


class ShellTool(BaseTool):
    """Execute a shell command through a sandboxed executor."""

    name: str = "shell"
    description: str = (
        "Execute a shell command via the runtime's sandboxed executor. Returns "
        "stdout/stderr and the exit code. Non-zero exits are reported as "
        "failures; the executor enforces the sandbox boundary."
    )
    shell_executor: Any = None  # async callable(command=...) -> {output, exit_code}

    class Config:
        arbitrary_types_allowed = True

    def _run(self, command: str, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(command=command, **kwargs))

    async def _arun(self, command: str, **kwargs: Any) -> str:
        if not self.shell_executor:
            return json.dumps({"error": "Shell executor is not configured"}, ensure_ascii=False)
        try:
            result = self.shell_executor(command=command)
            if inspect.isawaitable(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
