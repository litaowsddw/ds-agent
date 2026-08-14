"""Subagent fork tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-tool-subagent`` with the ``fork`` provider: a
child agent seeded with this conversation's completed turns, so it can build on
prior context without consuming this conversation's own context window.  The
fork executor is injected by the runtime (the parent's history is bound there);
an unconfigured tool fails honestly.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool


class SubagentForkTool(BaseTool):
    """Delegate to a subagent that inherits this conversation's completed turns."""

    name: str = "subagent_fork"
    description: str = (
        "Delegate a task to a subagent that inherits this conversation's completed "
        "turns (a fork). Use it for follow-up analysis, review, or continuation that "
        "builds on prior context without consuming this conversation's window. The "
        "subagent returns its result, not its intermediate steps."
    )
    subagent_fork_executor: Any = None  # async callable(task=..., subagent_kind=...) -> object

    class Config:
        arbitrary_types_allowed = True

    def _run(self, task: str, subagent_kind: str = "USER_SUB", **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(task=task, subagent_kind=subagent_kind, **kwargs))

    async def _arun(self, task: str, subagent_kind: str = "USER_SUB", **kwargs: Any) -> str:
        if not self.subagent_fork_executor:
            return json.dumps({"error": "Subagent fork executor is not configured"}, ensure_ascii=False)
        try:
            result = self.subagent_fork_executor(
                task=task, subagent_kind=subagent_kind or "USER_SUB"
            )
            if inspect.isawaitable(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
