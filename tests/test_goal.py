"""Goal lifecycle domain and its tool wrappers."""

import json

import pytest

from packages.runtime.goal import (
    GoalConflictError,
    GoalManager,
    GoalPhase,
)
from packages.runtime.tools.goal_tool import CreateGoalTool, GetGoalTool, UpdateGoalTool


def test_goal_create_and_get() -> None:
    manager = GoalManager()
    goal = manager.create("ship feature X", max_goal_rounds=5)

    assert goal.goal_id.startswith("goal_")
    assert goal.revision == 1
    assert goal.objective == "ship feature X"
    assert goal.max_goal_rounds == 5
    assert manager.get() == goal


def test_goal_update_bumps_revision_and_applies_each_action() -> None:
    manager = GoalManager()
    goal = manager.create("objective")

    paused = manager.update(goal_id=goal.goal_id, revision=1, action="pause")
    assert paused.phase is GoalPhase.PAUSED
    assert paused.revision == 2
    assert paused.armed is False

    resumed = manager.update(goal_id=goal.goal_id, revision=2, action="resume")
    assert resumed.phase is GoalPhase.ACTIVE
    assert resumed.armed is True
    assert resumed.revision == 3

    edited = manager.update(
        goal_id=goal.goal_id, revision=3, action="edit", objective="new objective"
    )
    assert edited.objective == "new objective"
    assert edited.revision == 4

    completed = manager.update(goal_id=goal.goal_id, revision=4, action="complete")
    assert completed.phase is GoalPhase.COMPLETED
    assert completed.revision == 5


def test_goal_update_rejects_stale_id_or_revision() -> None:
    manager = GoalManager()
    goal = manager.create("objective")

    with pytest.raises(GoalConflictError):
        manager.update(goal_id=goal.goal_id, revision=2, action="complete")
    with pytest.raises(GoalConflictError):
        manager.update(goal_id="wrong", revision=1, action="complete")


def test_goal_blocked_requires_minimum_rounds_and_reason() -> None:
    manager = GoalManager(min_blocked_rounds=3)
    goal = manager.create("objective")

    with pytest.raises(GoalConflictError):
        manager.update(
            goal_id=goal.goal_id, revision=1, action="blocked", blocker_reason="stuck"
        )

    manager.begin_round()
    manager.begin_round()
    manager.begin_round()  # rounds_started == 3; revision is still 1

    blocked = manager.update(
        goal_id=goal.goal_id, revision=1, action="blocked", blocker_reason="stuck"
    )
    assert blocked.phase is GoalPhase.BLOCKED
    assert blocked.blocker_reason == "stuck"

    # blocker_reason is mandatory even after the round gate
    manager2 = GoalManager(min_blocked_rounds=1)
    goal2 = manager2.create("objective")
    manager2.begin_round()
    with pytest.raises(ValueError):
        manager2.update(goal_id=goal2.goal_id, revision=1, action="blocked")


def test_goal_disarm_keeps_revision_stable() -> None:
    manager = GoalManager()
    goal = manager.create("objective")
    disarmed = manager.disarm()

    assert disarmed.armed is False
    assert disarmed.revision == goal.revision


@pytest.mark.asyncio
async def test_goal_tools_create_get_update_roundtrip() -> None:
    manager = GoalManager()
    create_tool = CreateGoalTool(goal_manager=manager)
    get_tool = GetGoalTool(goal_manager=manager)
    update_tool = UpdateGoalTool(goal_manager=manager)

    created = json.loads(await create_tool.ainvoke({"objective": "ship", "max_goal_rounds": 3}))
    assert created["objective"] == "ship"
    assert created["revision"] == 1
    goal_id = created["goal_id"]

    got = json.loads(await get_tool.ainvoke({}))
    assert got["goal_id"] == goal_id
    assert got["phase"] == "active"

    updated = json.loads(
        await update_tool.ainvoke({"goal_id": goal_id, "revision": 1, "action": "pause"})
    )
    assert updated["phase"] == "paused"
    assert updated["revision"] == 2


@pytest.mark.asyncio
async def test_goal_tools_fail_honestly_without_manager() -> None:
    assert json.loads(await CreateGoalTool().ainvoke({"objective": "x"})) == {
        "error": "Goal manager is not configured"
    }
    assert json.loads(await GetGoalTool().ainvoke({})) == {
        "error": "Goal manager is not configured"
    }
    assert json.loads(
        await UpdateGoalTool().ainvoke({"goal_id": "g", "revision": 1, "action": "complete"})
    ) == {"error": "Goal manager is not configured"}
