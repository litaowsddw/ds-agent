"""Goal round driver — models DeepSeek Harness ``dsh-goal-round-driver``.

The driver repeatedly runs one round toward the current goal while it is active
and armed, under the round cap.  It interprets each round's outcome:

- ``completed`` → mark the goal complete and stop.
- ``blocked``    → try to mark the goal blocked; the manager rejects this until
  the minimum-round gate has elapsed, so the same blocker must persist across
  rounds before the driver accepts it.
- ``continue``   → advance to the next round.

``run_round`` is injected by the runtime; the driver owns only the loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from packages.runtime.goal import Goal, GoalConflictError, GoalManager, GoalPhase


@dataclass(frozen=True, slots=True)
class GoalRoundOutcome:
    status: str  # completed | continue | blocked
    blocker_reason: str | None = None


@dataclass(frozen=True, slots=True)
class GoalDriveResult:
    status: str  # completed | blocked | round_limit | disarmed
    rounds_run: int
    blocker_reason: str | None = None


RunRoundFn = Callable[[Goal], Awaitable[GoalRoundOutcome] | GoalRoundOutcome]


class GoalRoundDriver:
    """Drive a goal through repeated rounds until a terminal state."""

    def __init__(self, goal_manager: GoalManager, run_round: RunRoundFn) -> None:
        self.goal_manager = goal_manager
        self.run_round = run_round

    async def drive(self) -> GoalDriveResult:
        current = self.goal_manager.get()
        if current is None:
            raise GoalConflictError("no goal exists")

        rounds_run = 0
        while current.phase is GoalPhase.ACTIVE:
            if not current.armed:
                return GoalDriveResult("disarmed", rounds_run)
            if current.max_goal_rounds is not None and rounds_run >= current.max_goal_rounds:
                return GoalDriveResult("round_limit", rounds_run)

            current = self.goal_manager.begin_round()
            outcome = await self.run_round(current)
            rounds_run += 1

            if outcome.status == "completed":
                self.goal_manager.update(
                    goal_id=current.goal_id,
                    revision=current.revision,
                    action="complete",
                )
                return GoalDriveResult("completed", rounds_run)

            if outcome.status == "blocked":
                try:
                    self.goal_manager.update(
                        goal_id=current.goal_id,
                        revision=current.revision,
                        action="blocked",
                        blocker_reason=outcome.blocker_reason,
                    )
                except GoalConflictError:
                    # Minimum-round gate not met yet; keep driving so the same
                    # blocker has to persist across rounds.
                    current = self.goal_manager.get() or current
                    continue
                return GoalDriveResult("blocked", rounds_run, outcome.blocker_reason)

            # status == "continue": loop around.
            current = self.goal_manager.get() or current

        if current.phase is GoalPhase.COMPLETED:
            return GoalDriveResult("completed", rounds_run)
        if current.phase is GoalPhase.BLOCKED:
            return GoalDriveResult("blocked", rounds_run, current.blocker_reason)
        return GoalDriveResult("disarmed", rounds_run)
