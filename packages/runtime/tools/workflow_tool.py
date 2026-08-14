"""Workflow tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-tool-workflow``, but as a safe declarative fan-out
instead of arbitrary script execution.  The tool accepts a list of phases (each
with parallel agent tasks) and runs them through an injected ``WorkflowRunner``.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from packages.runtime.workflow_runner import WorkflowPhase, WorkflowTask


class _TaskArgs(BaseModel):
    prompt: str = Field(description="The complete standalone prompt for one subagent.")
    result_schema: dict[str, Any] | None = Field(
        default=None, description="Optional JSON schema for a structured result."
    )


class _PhaseArgs(BaseModel):
    title: str = Field(description="Progress-group title for this phase.")
    tasks: list[_TaskArgs] = Field(description="Tasks run in parallel within this phase.")


class _WorkflowArgs(BaseModel):
    phases: list[_PhaseArgs] = Field(
        description="Phases run sequentially; tasks within a phase run in parallel."
    )


def _get(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


class WorkflowTool(BaseTool):
    """Fan out work across many subagents as parallel phases."""

    name: str = "workflow"
    description: str = (
        "Fan out work across many subagents in phases. Each phase has a title and "
        "a list of tasks (prompt + optional result_schema); tasks within a phase "
        "run in parallel, phases run sequentially. A failing subagent yields null."
    )
    args_schema: type[BaseModel] = _WorkflowArgs
    workflow_runner: Any = None  # object with run_phases(list[WorkflowPhase]) -> list

    class Config:
        arbitrary_types_allowed = True

    def _run(self, phases: list[dict[str, Any]], **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(phases=phases, **kwargs))

    async def _arun(self, phases: list[dict[str, Any]], **kwargs: Any) -> str:
        if not self.workflow_runner:
            return json.dumps({"error": "Workflow runner is not configured"}, ensure_ascii=False)
        try:
            normalized = [
                WorkflowPhase(
                    title=str(_get(phase, "title", "") or ""),
                    tasks=[
                        WorkflowTask(
                            prompt=str(_get(task, "prompt", "") or ""),
                            schema=_get(task, "result_schema"),
                        )
                        for task in (_get(phase, "tasks") or [])
                    ],
                )
                for phase in (phases or [])
            ]
            results = await self.workflow_runner.run_phases(normalized)
            return json.dumps(results, ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
