"""Subagent delegation tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-tool-subagent`` (spawn provider): delegate a
self-contained task to a child agent that runs in its own context and returns
its result.  The executor is injected by the runtime; an unconfigured tool
fails honestly instead of fabricating a delegate result.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool


class SpawnSubagentTool(BaseTool):
    """Delegate a self-contained task to a subagent and return its result."""

    name: str = "spawn_subagent"
    description: str = (
        "Delegate a self-contained task to a subagent that works in its own "
        "context and does not see this conversation. Provide a complete, "
        "standalone prompt and an optional subagent_kind (USER_SUB, SYSTEM_RAG, "
        "SYSTEM_SKILL, SYSTEM_TOOL). Returns the subagent's result, not its "
        "intermediate steps."
    )
    subagent_executor: Any = None  # async callable(task=..., subagent_kind=...) -> object

    class Config:
        arbitrary_types_allowed = True

    def _run(self, task: str, subagent_kind: str = "USER_SUB", **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(task=task, subagent_kind=subagent_kind, **kwargs))

    async def _arun(self, task: str, subagent_kind: str = "USER_SUB", **kwargs: Any) -> str:
        if not self.subagent_executor:
            return json.dumps({"error": "Subagent executor is not configured"}, ensure_ascii=False)
        try:
            result = self.subagent_executor(task=task, subagent_kind=subagent_kind or "USER_SUB")
            if inspect.isawaitable(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
