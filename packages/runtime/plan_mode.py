"""Plan mode state — models DeepSeek Harness ``dsh-plan-mode``.

Plan mode is a per-agent boolean: while active the agent explores and produces
a decision-complete plan, and only ``exit_plan_mode`` (which submits the plan
for approval and leaves the mode) ends it.  The manager is storage-agnostic so
the runtime can bind it to session state without coupling the mode to a store.
"""

from __future__ import annotations


class PlanModeManager:
    """Track plan-mode state and the single submitted plan."""

    def __init__(self) -> None:
        self._active = False
        self._plan: str | None = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def plan(self) -> str | None:
        return self._plan

    def enter(self) -> None:
        """Begin plan mode; any previously submitted plan is cleared."""

        self._active = True
        self._plan = None

    def exit(self, plan: str) -> str:
        """Submit the plan, leave plan mode, and return the accepted plan text."""

        normalized = (plan or "").strip()
        if not normalized:
            raise ValueError("plan must be a non-empty string")
        self._plan = normalized
        self._active = False
        return normalized

    def snapshot(self) -> dict[str, object]:
        return {"active": self._active, "plan": self._plan}
