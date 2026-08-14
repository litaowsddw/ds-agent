"""Web search tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-tool-web``: the search backend is injected by the
runtime.  Without a configured accessor the tool fails honestly instead of
fabricating results.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool


class WebSearchTool(BaseTool):
    """Search the web through a runtime-injected search backend."""

    name: str = "web_search"
    description: str = (
        "Search the web for current information. Returns an optional summary plus "
        "a list of source URLs. Use it when the request needs up-to-date facts that "
        "the local context cannot answer."
    )
    web_search_accessor: Any = None  # optional async callable(query=...) -> object

    class Config:
        arbitrary_types_allowed = True

    def _run(self, query: str, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(query=query, **kwargs))

    async def _arun(self, query: str, **kwargs: Any) -> str:
        if not self.web_search_accessor:
            return json.dumps(
                {"error": "Web search accessor is not configured"}, ensure_ascii=False
            )
        try:
            result = self.web_search_accessor(query=query)
            if inspect.isawaitable(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
