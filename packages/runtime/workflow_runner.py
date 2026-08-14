"""Workflow fan-out runner — models DeepSeek Harness ``dsh-workflow`` safely.

DSH's workflow lets an agent author a fan-out script with ``agent`` /
``pipeline`` / ``parallel`` / ``phase`` hooks.  Executing arbitrary code is a
boundary AgentFlow does not cross; this module exposes the same orchestration
shapes as a declarative runner: phases of parallel agent tasks, plus an
item-through-stages pipeline with no barrier between stages.  The per-task
``agent`` is injected by the runtime.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


AgentFn = Callable[[str, dict[str, Any] | None], Awaitable[Any] | Any]
StageFn = Callable[[Any, Any], Awaitable[Any] | Any]


@dataclass(frozen=True, slots=True)
class WorkflowTask:
    """One agent task, optionally with a JSON schema for its structured result."""

    prompt: str
    schema: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class WorkflowPhase:
    """A progress group of tasks run in parallel."""

    title: str
    tasks: list[WorkflowTask]


class WorkflowRunner:
    """Fan out work across subagents with phases, parallelism, and pipelines."""

    def __init__(self, agent: AgentFn) -> None:
        self.agent = agent

    async def run_task(self, task: WorkflowTask) -> Any:
        try:
            return await self.agent(task.prompt, task.schema)
        except Exception:
            # A failing agent yields null, mirroring DSH's `.filter(Boolean)`.
            return None

    async def parallel(self, tasks: list[WorkflowTask]) -> list[Any]:
        return await asyncio.gather(*(self.run_task(task) for task in tasks))

    async def run_phases(self, phases: list[WorkflowPhase]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for phase in phases:
            phase_results = await self.parallel(phase.tasks)
            results.append({"title": phase.title, "results": phase_results})
        return results

    async def pipeline(self, items: list[Any], stages: list[StageFn]) -> list[Any]:
        """Run each item through every stage independently (no barrier)."""

        async def run_item(item: Any) -> Any:
            previous: Any = None
            for stage in stages:
                try:
                    previous = await stage(previous, item)
                except Exception:
                    return None
            return previous

        return await asyncio.gather(*(run_item(item) for item in items))
