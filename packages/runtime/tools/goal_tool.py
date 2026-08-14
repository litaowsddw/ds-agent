"""Goal tools → LangChain BaseTool wrappers.

Models DeepSeek Harness ``dsh-tool-goal``: three model-facing tools
(create_goal / get_goal / update_goal) that wrap a runtime-injected
``GoalManager``.  They never fabricate goal state; an unconfigured manager
fails honestly.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool


def _json_or_error(value: object) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


class CreateGoalTool(BaseTool):
    """Create one same-session completion goal."""

    name: str = "create_goal"
    description: str = (
        "Create one persisted completion goal for the current long-running "
        "objective. Provide the concrete objective and an optional positive "
        "round cap; returns the goal snapshot (goal_id, revision, phase)."
    )
    goal_manager: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, objective: str, max_goal_rounds: int | None = None, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(objective=objective, max_goal_rounds=max_goal_rounds, **kwargs))

    async def _arun(self, objective: str, max_goal_rounds: int | None = None, **kwargs: Any) -> str:
        if not self.goal_manager:
            return json.dumps({"error": "Goal manager is not configured"}, ensure_ascii=False)
        try:
            goal = self.goal_manager.create(objective, max_goal_rounds)
            return _json_or_error(goal.as_dict())
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


class GetGoalTool(BaseTool):
    """Read the current goal snapshot."""

    name: str = "get_goal"
    description: str = (
        "Read the current completion goal (id, revision, objective, phase, round "
        "count, limit, blocker, armed). Returns null when no goal exists."
    )
    goal_manager: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> str:
        if not self.goal_manager:
            return json.dumps({"error": "Goal manager is not configured"}, ensure_ascii=False)
        try:
            goal = self.goal_manager.get()
            return json.dumps(goal.as_dict() if goal is not None else None, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


class UpdateGoalTool(BaseTool):
    """Apply one lifecycle action to the current goal."""

    name: str = "update_goal"
    description: str = (
        "Update the exact current goal revision. action is one of: edit, pause, "
        "resume, complete, blocked. goal_id and revision must match the current "
        "goal exactly; complete only when the objective is achieved; blocked "
        "requires blocker_reason and enough elapsed rounds."
    )
    goal_manager: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(
        self,
        goal_id: str,
        revision: int,
        action: str,
        objective: str | None = None,
        max_goal_rounds: int | None = None,
        blocker_reason: str | None = None,
        **kwargs: Any,
    ) -> str:
        import asyncio

        return asyncio.run(
            self._arun(
                goal_id=goal_id,
                revision=revision,
                action=action,
                objective=objective,
                max_goal_rounds=max_goal_rounds,
                blocker_reason=blocker_reason,
                **kwargs,
            )
        )

    async def _arun(
        self,
        goal_id: str,
        revision: int,
        action: str,
        objective: str | None = None,
        max_goal_rounds: int | None = None,
        blocker_reason: str | None = None,
        **kwargs: Any,
    ) -> str:
        if not self.goal_manager:
            return json.dumps({"error": "Goal manager is not configured"}, ensure_ascii=False)
        try:
            goal = self.goal_manager.update(
                goal_id=goal_id,
                revision=int(revision),
                action=action,
                objective=objective,
                max_goal_rounds=max_goal_rounds,
                blocker_reason=blocker_reason,
            )
            return _json_or_error(goal.as_dict())
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
