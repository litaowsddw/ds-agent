"""Workflow fan-out runner."""

import asyncio
import json

import pytest

from packages.runtime.workflow_runner import (
    WorkflowPhase,
    WorkflowRunner,
    WorkflowTask,
)
from packages.runtime.tools.workflow_tool import WorkflowTool


@pytest.mark.asyncio
async def test_parallel_runs_tasks_and_nullifies_failures() -> None:
    async def agent(prompt: str, schema=None):
        if prompt == "fail":
            raise RuntimeError("boom")
        return {"prompt": prompt, "schema": schema}

    runner = WorkflowRunner(agent)
    results = await runner.parallel(
        [
            WorkflowTask("a"),
            WorkflowTask("fail"),
            WorkflowTask("b", {"type": "object"}),
        ]
    )

    assert results[0] == {"prompt": "a", "schema": None}
    assert results[1] is None  # a failing agent resolves to null
    assert results[2]["schema"] == {"type": "object"}


@pytest.mark.asyncio
async def test_run_phases_groups_parallel_results_by_phase() -> None:
    async def agent(prompt: str, schema=None):
        return prompt

    runner = WorkflowRunner(agent)
    phases = [
        WorkflowPhase("phase1", [WorkflowTask("t1"), WorkflowTask("t2")]),
        WorkflowPhase("phase2", [WorkflowTask("t3")]),
    ]
    results = await runner.run_phases(phases)

    assert [phase["title"] for phase in results] == ["phase1", "phase2"]
    assert results[0]["results"] == ["t1", "t2"]
    assert results[1]["results"] == ["t3"]


@pytest.mark.asyncio
async def test_pipeline_runs_items_through_stages_independently() -> None:
    async def stage_add(previous, item):
        await asyncio.sleep(0)
        return (previous or 0) + item

    runner = WorkflowRunner(agent=None)
    results = await runner.pipeline([1, 2, 3], [stage_add, stage_add])

    assert results == [2, 4, 6]


@pytest.mark.asyncio
async def test_pipeline_skips_remaining_stages_on_failure() -> None:
    async def stage_ok(previous, item):
        return (previous or "") + str(item)

    async def stage_boom(previous, item):
        raise RuntimeError("boom")

    runner = WorkflowRunner(agent=None)
    results = await runner.pipeline(["x"], [stage_boom, stage_ok])

    assert results == [None]


@pytest.mark.asyncio
async def test_workflow_tool_runs_phases_and_fails_honestly() -> None:
    async def agent(prompt: str, schema=None):
        return {"done": prompt}

    runner = WorkflowRunner(agent)
    tool = WorkflowTool(workflow_runner=runner)
    result = json.loads(await tool.ainvoke({"phases": [
        {"title": "p1", "tasks": [{"prompt": "a"}, {"prompt": "b"}]},
    ]}))

    assert result[0]["title"] == "p1"
    assert result[0]["results"] == [{"done": "a"}, {"done": "b"}]

    assert json.loads(await WorkflowTool().ainvoke({"phases": []})) == {
        "error": "Workflow runner is not configured"
    }
