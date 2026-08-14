"""Goal round driver."""

import pytest

from packages.runtime.goal import GoalManager
from packages.runtime.goal_round_driver import (
    GoalRoundDriver,
    GoalRoundOutcome,
)


@pytest.mark.asyncio
async def test_driver_completes_goal_on_first_round() -> None:
    manager = GoalManager()
    manager.create("ship X", max_goal_rounds=10)

    async def run_round(goal):
        return GoalRoundOutcome("completed")

    result = await GoalRoundDriver(manager, run_round).drive()

    assert result.status == "completed"
    assert result.rounds_run == 1
    assert manager.get().phase.value == "completed"


@pytest.mark.asyncio
async def test_driver_blocks_after_minimum_rounds() -> None:
    manager = GoalManager(min_blocked_rounds=3)
    manager.create("ship X")

    async def run_round(goal):
        return GoalRoundOutcome("blocked", blocker_reason="no access")

    result = await GoalRoundDriver(manager, run_round).drive()

    assert result.status == "blocked"
    assert result.rounds_run == 3
    assert result.blocker_reason == "no access"
    assert manager.get().blocker_reason == "no access"


@pytest.mark.asyncio
async def test_driver_continues_then_completes() -> None:
    manager = GoalManager()
    manager.create("ship X")
    seen: list[int] = []

    async def run_round(goal):
        seen.append(goal.rounds_started)
        return GoalRoundOutcome("completed" if goal.rounds_started >= 2 else "continue")

    result = await GoalRoundDriver(manager, run_round).drive()

    assert result.status == "completed"
    assert result.rounds_run == 2
    assert seen == [1, 2]


@pytest.mark.asyncio
async def test_driver_stops_when_disarmed() -> None:
    manager = GoalManager()
    manager.create("ship X")
    manager.disarm()

    async def run_round(goal):
        return GoalRoundOutcome("completed")

    result = await GoalRoundDriver(manager, run_round).drive()

    assert result.status == "disarmed"
    assert result.rounds_run == 0


@pytest.mark.asyncio
async def test_driver_stops_at_round_limit() -> None:
    manager = GoalManager()
    manager.create("ship X", max_goal_rounds=2)

    async def run_round(goal):
        return GoalRoundOutcome("continue")

    result = await GoalRoundDriver(manager, run_round).drive()

    assert result.status == "round_limit"
    assert result.rounds_run == 2
