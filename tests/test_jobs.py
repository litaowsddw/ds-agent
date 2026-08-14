"""Background job registry and its tool wrappers."""

import asyncio
import json

import pytest

from packages.runtime.jobs import JobRegistry
from packages.runtime.tools.jobs_tool import KillJobTool, ListJobsTool, ReadJobOutputTool


@pytest.mark.asyncio
async def test_job_registry_runs_finishes_and_lists() -> None:
    registry = JobRegistry()

    async def work() -> str:
        await asyncio.sleep(0)
        return "done"

    job = registry.start("test", work())
    await registry.join(job.job_id)

    assert job.status == "finished"
    assert job.output == "done"
    listed = registry.list()
    assert len(listed) == 1
    assert listed[0]["status"] == "finished"


@pytest.mark.asyncio
async def test_job_registry_kill_cancels_running_job() -> None:
    registry = JobRegistry()

    async def long_work() -> None:
        await asyncio.sleep(10)

    job = registry.start("long", long_work())
    await asyncio.sleep(0)  # let the runner reach its first await
    assert job.status == "running"

    assert await registry.kill(job.job_id) is True
    await registry.join(job.job_id)
    assert job.status == "killed"


@pytest.mark.asyncio
async def test_job_tools_list_read_and_kill() -> None:
    registry = JobRegistry()

    async def work() -> str:
        return "hello"

    job = registry.start("t", work())
    await registry.join(job.job_id)

    listed = json.loads(await ListJobsTool(job_registry=registry).ainvoke({}))
    assert listed[0]["output"] == "hello"

    out = json.loads(
        await ReadJobOutputTool(job_registry=registry).ainvoke({"job_id": listed[0]["job_id"]})
    )
    assert out["status"] == "finished"

    assert json.loads(await ListJobsTool().ainvoke({})) == {
        "error": "Job registry is not configured"
    }


@pytest.mark.asyncio
async def test_kill_job_tool_reports_cancellation() -> None:
    registry = JobRegistry()

    async def long_work() -> None:
        await asyncio.sleep(10)

    job = registry.start("long", long_work())
    result = json.loads(await KillJobTool(job_registry=registry).ainvoke({"job_id": job.job_id}))

    assert result["cancelled"] is True
    await registry.join(job.job_id)
    assert job.status == "killed"
