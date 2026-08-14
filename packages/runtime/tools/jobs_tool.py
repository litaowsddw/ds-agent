"""Background job tools → LangChain BaseTool wrappers.

Models DeepSeek Harness ``dsh-tool-jobs``: list / read-output / kill control
over a runtime-injected ``JobRegistry``.  Starting a job remains a runtime
concern (a tool runs in background); these tools only observe and stop.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool


class ListJobsTool(BaseTool):
    """List background jobs and their statuses."""

    name: str = "list_jobs"
    description: str = "List background jobs (id, kind, status) owned by this agent."
    job_registry: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs: Any) -> str:
        return _call(self.job_registry, lambda r: r.list())

    async def _arun(self, **kwargs: Any) -> str:
        return _call(self.job_registry, lambda r: r.list())


class ReadJobOutputTool(BaseTool):
    """Read a background job's accumulated output."""

    name: str = "read_job_output"
    description: str = (
        "Read a background job's current status, output, and error by job id."
    )
    job_registry: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, job_id: str, **kwargs: Any) -> str:
        return _call(self.job_registry, lambda r: r.output(job_id))

    async def _arun(self, job_id: str, **kwargs: Any) -> str:
        return _call(self.job_registry, lambda r: r.output(job_id))


class KillJobTool(BaseTool):
    """Cancel a running background job."""

    name: str = "kill_job"
    description: str = "Cancel a running background job by job id."
    job_registry: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, job_id: str, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(job_id=job_id, **kwargs))

    async def _arun(self, job_id: str, **kwargs: Any) -> str:
        if not self.job_registry:
            return json.dumps({"error": "Job registry is not configured"}, ensure_ascii=False)
        try:
            cancelled = await self.job_registry.kill(job_id)
            return json.dumps({"job_id": job_id, "cancelled": cancelled}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _call(registry: Any, operation: Any) -> str:
    if registry is None:
        return json.dumps({"error": "Job registry is not configured"}, ensure_ascii=False)
    try:
        result = operation(registry)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
