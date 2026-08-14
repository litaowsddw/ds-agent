"""Subagent-control tools → LangChain BaseTool wrappers.

Models DeepSeek Harness ``dsh-tool-subagent-control``: these tools expose the
delegation surface to the agent without owning the subagent registry.  The
lister is injected by the runtime (usually the Agent's ``SubAgentRegistry``).
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool


class ListSubagentsTool(BaseTool):
    """List the subagents the current Agent can delegate to."""

    name: str = "list_subagents"
    description: str = (
        "List the subagents available to delegate work to (id, name, description, "
        "kind). Use it to choose the right delegate before dispatching a subtask."
    )
    subagent_lister: Any = None  # optional async callable() -> list[dict]

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> str:
        if not self.subagent_lister:
            return json.dumps(
                {"error": "Subagent lister is not configured"}, ensure_ascii=False
            )
        try:
            result = self.subagent_lister()
            if inspect.isawaitable(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
