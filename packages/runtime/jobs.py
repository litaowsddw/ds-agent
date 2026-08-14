"""Background job registry — models DeepSeek Harness ``dsh-jobs``.

The registry owns job state (running/finished/failed/killed) and the asyncio
tasks that drive them.  A runner settles the terminal status synchronously with
the task's completion (no deferred callback), so ``join`` observes a settled
snapshot immediately.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4


@dataclass
class Job:
    job_id: str
    kind: str
    status: str  # running | finished | failed | killed
    output: str = ""
    error: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "output": self.output,
            "error": self.error,
        }


class JobRegistry:
    """In-memory registry of background jobs and their driving tasks."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, kind: str, coro) -> Job:
        """Register and launch a background awaitable; returns the job handle."""

        job_id = f"job_{uuid4().hex[:12]}"
        job = Job(job_id=job_id, kind=kind, status="running")
        self._jobs[job_id] = job
        self._tasks[job_id] = asyncio.create_task(self._runner(job_id, coro))
        return job

    async def _runner(self, job_id: str, coro) -> None:
        job = self._jobs[job_id]
        try:
            output = await coro
            job.output = "" if output is None else str(output)
            job.status = "finished"
        except asyncio.CancelledError:
            job.status = "killed"
            self._close(coro)
            raise
        except Exception as exc:  # noqa: BLE001 - record terminal failure
            job.status = "failed"
            job.error = str(exc)

    @staticmethod
    def _close(coro) -> None:
        close = getattr(coro, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                pass

    def list(self) -> list[dict[str, str]]:
        return [job.as_dict() for job in self._jobs.values()]

    def output(self, job_id: str) -> dict[str, str] | None:
        job = self._jobs.get(job_id)
        return job.as_dict() if job is not None else None

    async def join(self, job_id: str) -> dict[str, str]:
        """Await the job's terminal state and return its settled snapshot."""

        task = self._tasks.get(job_id)
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
        return self.output(job_id) or {}

    async def kill(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True
