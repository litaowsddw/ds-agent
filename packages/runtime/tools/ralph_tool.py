"""Ralph tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-tool-ralph``: run a foreground fresh-agent
iteration loop toward one immutable objective.  The loop runner is injected by
the runtime (usually a ``RalphLoop``); an unconfigured tool fails honestly.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool


class RalphTool(BaseTool):
    """Run a fresh-agent iteration loop toward one immutable objective."""

    name: str = "ralph"
    description: str = (
        "Run a foreground fresh-agent iteration loop toward one immutable "
        "objective. Each round opens a fresh agent with no prior conversation; "
        "the shared workspace is durable memory. Stops when a round reports "
        "completion or a concrete blocker, or at the round limit."
    )
    ralph_runner: Any = None  # async callable(objective=..., max_rounds=...) -> object

    class Config:
        arbitrary_types_allowed = True

    def _run(self, objective: str, max_rounds: int | None = None, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(objective=objective, max_rounds=max_rounds, **kwargs))

    async def _arun(self, objective: str, max_rounds: int | None = None, **kwargs: Any) -> str:
        if not self.ralph_runner:
            return json.dumps({"error": "Ralph runner is not configured"}, ensure_ascii=False)
        try:
            result = self.ralph_runner(objective=objective, max_rounds=max_rounds)
            if inspect.isawaitable(result):
                result = await result
            if hasattr(result, "as_dict"):
                result = result.as_dict()
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
