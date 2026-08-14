"""Goal lifecycle domain — models DeepSeek Harness ``dsh-goal``.

A Goal tracks one same-session completion objective through an explicit
lifecycle (create → get → update with edit/pause/resume/complete/blocked).
The manager enforces optimistic concurrency on ``(goal_id, revision)`` and the
minimum-round gate for ``blocked``; it is deliberately storage-agnostic so the
runtime can persist it to the session store without coupling the state machine
to a database.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import uuid4


class GoalPhase(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class GoalAction(StrEnum):
    EDIT = "edit"
    PAUSE = "pause"
    RESUME = "resume"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class GoalConflictError(ValueError):
    """Raised when a goal update targets a stale id or revision."""


@dataclass(frozen=True, slots=True)
class Goal:
    """An immutable goal snapshot; every update produces a new revision."""

    goal_id: str
    revision: int
    objective: str
    phase: GoalPhase = GoalPhase.ACTIVE
    rounds_started: int = 0
    max_goal_rounds: int | None = None
    blocker_reason: str | None = None
    armed: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "goal_id": self.goal_id,
            "revision": self.revision,
            "objective": self.objective,
            "phase": str(self.phase),
            "rounds_started": self.rounds_started,
            "max_goal_rounds": self.max_goal_rounds,
            "blocker_reason": self.blocker_reason,
            "armed": self.armed,
        }


class GoalManager:
    """Single-current-goal state machine with optimistic concurrency."""

    def __init__(self, min_blocked_rounds: int = 3) -> None:
        self._goal: Goal | None = None
        self._min_blocked_rounds = max(1, int(min_blocked_rounds))

    @property
    def current(self) -> Goal | None:
        return self._goal

    def create(self, objective: str, max_goal_rounds: int | None = None) -> Goal:
        """Create the single completion goal for the session."""

        normalized = (objective or "").strip()
        if not normalized:
            raise ValueError("objective must be a non-empty string")
        self._goal = Goal(
            goal_id=f"goal_{uuid4().hex[:16]}",
            revision=1,
            objective=normalized,
            max_goal_rounds=_positive_int_or_none(max_goal_rounds),
            armed=True,
        )
        return self._goal

    def get(self) -> Goal | None:
        return self._goal

    def begin_round(self) -> Goal:
        """Advance the round counter; called by the runtime round driver."""

        if self._goal is None:
            raise GoalConflictError("no goal exists")
        self._goal = replace(self._goal, rounds_started=self._goal.rounds_started + 1)
        return self._goal

    def disarm(self) -> Goal:
        """Disarm automatic continuation (session resume/fork)."""

        if self._goal is None:
            raise GoalConflictError("no goal exists")
        self._goal = replace(self._goal, armed=False)
        return self._goal

    def update(
        self,
        *,
        goal_id: str,
        revision: int,
        action: GoalAction | str,
        objective: str | None = None,
        max_goal_rounds: int | None = None,
        blocker_reason: str | None = None,
    ) -> Goal:
        """Apply one lifecycle action and return the new revision."""

        goal = self._require_match(goal_id, revision)
        action = GoalAction(str(action))

        if action is GoalAction.EDIT:
            next_objective = (objective or goal.objective).strip()
            if not next_objective:
                raise ValueError("objective must be a non-empty string")
            next_max = (
                _positive_int_or_none(max_goal_rounds)
                if max_goal_rounds is not None
                else goal.max_goal_rounds
            )
            updated = replace(goal, objective=next_objective, max_goal_rounds=next_max)
        elif action is GoalAction.PAUSE:
            updated = replace(goal, phase=GoalPhase.PAUSED, armed=False)
        elif action is GoalAction.RESUME:
            updated = replace(goal, phase=GoalPhase.ACTIVE, armed=True)
        elif action is GoalAction.COMPLETE:
            updated = replace(goal, phase=GoalPhase.COMPLETED, armed=False)
        elif action is GoalAction.BLOCKED:
            if goal.rounds_started < self._min_blocked_rounds:
                raise GoalConflictError(
                    f"blocked requires at least {self._min_blocked_rounds} rounds"
                )
            reason = (blocker_reason or "").strip()
            if not reason:
                raise ValueError("blocker_reason is required for blocked")
            updated = replace(
                goal, phase=GoalPhase.BLOCKED, blocker_reason=reason, armed=False
            )
        else:
            raise ValueError(f"unknown action: {action}")

        self._goal = replace(updated, revision=goal.revision + 1)
        return self._goal

    def _require_match(self, goal_id: str, revision: int) -> Goal:
        if self._goal is None:
            raise GoalConflictError("no goal exists")
        if self._goal.goal_id != goal_id:
            raise GoalConflictError("goal id does not match the current goal")
        if self._goal.revision != revision:
            raise GoalConflictError("goal revision does not match the current goal")
        return self._goal


def _positive_int_or_none(value: int | None) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("max_goal_rounds must be a positive integer")
    return parsed
