"""Plan mode tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-plan-mode``: a single ``exit_plan_mode`` tool that
submits the decision-complete plan and leaves plan mode.  It never fabricates
approval; an unconfigured manager fails honestly.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool


class ExitPlanModeTool(BaseTool):
    """Submit the plan for approval and leave plan mode."""

    name: str = "exit_plan_mode"
    description: str = (
        "Present the complete implementation plan for review and leave plan mode. "
        "The plan must be decision-complete markdown starting with a # title; use "
        "this as the only and final tool call of the response. Implementation "
        "begins only after approval."
    )
    plan_mode_manager: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, plan: str, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(plan=plan, **kwargs))

    async def _arun(self, plan: str, **kwargs: Any) -> str:
        if not self.plan_mode_manager:
            return json.dumps({"error": "Plan mode manager is not configured"}, ensure_ascii=False)
        try:
            submitted = self.plan_mode_manager.exit(plan)
            return json.dumps({"status": "submitted", "plan": submitted}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
