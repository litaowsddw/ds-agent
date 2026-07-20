"""Skill discovery tool exposed to a LangChain/LangGraph Agent."""

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool


class SkillSearchTool(BaseTool):
    """Find skills the current Agent is already allowed to use.

    The accessor is injected by the runtime.  The tool cannot create access to
    a skill; it can only return the agent-scoped catalogue supplied by the
    server.
    """

    name: str = "skill_search"
    description: str = (
        "Search the current Agent's authorized Skill catalogue by task or keyword. "
        "Returns metadata only; load or create a Skill through its dedicated runtime path."
    )
    org_id: str = ""
    agent_id: str = ""
    skill_accessor: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, query: str, top_k: int = 5, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(query=query, top_k=top_k, **kwargs))

    async def _arun(self, query: str, top_k: int = 5, **kwargs: Any) -> str:
        if not self.skill_accessor:
            return json.dumps({"error": "Skill accessor is not configured"}, ensure_ascii=False)
        try:
            result = self.skill_accessor(
                query=query,
                org_id=self.org_id,
                agent_id=self.agent_id,
                top_k=max(1, min(int(top_k), 20)),
            )
            if inspect.isawaitable(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
