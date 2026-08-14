"""Fresh-agent iteration loop (Ralph)."""

import json

import pytest

from packages.runtime.ralph import RalphLoop, RalphRoundResult
from packages.runtime.tools.ralph_tool import RalphTool


@pytest.mark.asyncio
async def test_ralph_completes_and_carries_memory_forward() -> None:
    calls: list[tuple[int, str]] = []

    async def run_round(index: int, objective: str, memory: str) -> RalphRoundResult:
        calls.append((index, memory))
        if index == 1:
            return RalphRoundResult("continue", "found a lead")
        return RalphRoundResult("completed", "done")

    report = await RalphLoop(run_round, max_rounds=5).run("solve X")

    assert report.status == "completed"
    assert report.rounds == 2
    assert calls == [(1, ""), (2, "found a lead")]


@pytest.mark.asyncio
async def test_ralph_blocks_with_concrete_reason() -> None:
    async def run_round(index: int, objective: str, memory: str) -> RalphRoundResult:
        return RalphRoundResult("blocked", "stuck", "missing dependency")

    report = await RalphLoop(run_round, max_rounds=5).run("solve X")

    assert report.status == "blocked"
    assert report.blocker_reason == "missing dependency"


@pytest.mark.asyncio
async def test_ralph_stops_at_round_limit_with_last_memory() -> None:
    async def run_round(index: int, objective: str, memory: str) -> RalphRoundResult:
        return RalphRoundResult("continue", f"round {index}")

    report = await RalphLoop(run_round, max_rounds=3).run("solve X")

    assert report.status == "round_limit"
    assert report.rounds == 3
    assert report.final_report == "round 3"


@pytest.mark.asyncio
async def test_ralph_tool_runs_loop_and_fails_honestly() -> None:
    async def runner(objective: str, max_rounds: int | None) -> dict:
        return {"status": "completed", "rounds": 1, "final_report": None, "blocker_reason": None}

    tool = RalphTool(ralph_runner=runner)
    result = json.loads(await tool.ainvoke({"objective": "solve X"}))
    assert result["status"] == "completed"

    assert json.loads(await RalphTool().ainvoke({"objective": "x"})) == {
        "error": "Ralph runner is not configured"
    }
