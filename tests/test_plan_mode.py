"""Plan mode contract, manager, and exit_plan_mode tool."""

import json

import pytest

from packages.runtime.plan_mode import PlanModeManager
from packages.runtime.system_prompt import PLAN_MODE_CONTRACT, build_agent_system_prompt
from packages.runtime.tools.plan_mode_tool import ExitPlanModeTool


def test_plan_mode_contract_is_injected_only_when_requested() -> None:
    plain = build_agent_system_prompt(agent_name="A")
    assert "[Plan mode]" not in plain

    planned = build_agent_system_prompt(agent_name="A", plan_mode=True)
    assert "[Plan mode]" in planned
    assert "exit_plan_mode" in planned
    assert "decision-complete" in planned


def test_plan_mode_contract_references_agentflow_not_foreign_tools() -> None:
    # The contract must stay honest: it only names exit_plan_mode, never a tool
    # AgentFlow does not provide (e.g. todo_write is not referenced here).
    assert "exit_plan_mode" in PLAN_MODE_CONTRACT
    assert "Do not use todo_write to track this planning phase" not in PLAN_MODE_CONTRACT


def test_plan_mode_manager_enter_exit_lifecycle() -> None:
    manager = PlanModeManager()
    assert manager.active is False

    manager.enter()
    assert manager.active is True

    plan = manager.exit("# Ship feature\n\n## Changes\n...")
    assert manager.active is False
    assert manager.plan == plan

    # Re-entering clears any previously submitted plan.
    manager.enter()
    assert manager.plan is None


def test_plan_mode_manager_rejects_empty_plan() -> None:
    manager = PlanModeManager()
    manager.enter()
    with pytest.raises(ValueError):
        manager.exit("   ")


@pytest.mark.asyncio
async def test_exit_plan_mode_tool_submits_plan_and_leaves_mode() -> None:
    manager = PlanModeManager()
    manager.enter()
    tool = ExitPlanModeTool(plan_mode_manager=manager)

    result = json.loads(await tool.ainvoke({"plan": "# Plan\n..."}))
    assert result["status"] == "submitted"
    assert manager.active is False


@pytest.mark.asyncio
async def test_exit_plan_mode_tool_fails_honestly_without_manager() -> None:
    result = json.loads(await ExitPlanModeTool().ainvoke({"plan": "# Plan"}))
    assert result == {"error": "Plan mode manager is not configured"}
