"""Structured task-list tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-tool-todo``: the agent sends the ENTIRE list on
every call and it REPLACES the previous list — there are no partial updates and
no per-item edits.  The store is injected by the runtime; without one the tool
keeps an in-memory list for the lifetime of the Agent runtime instance.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class _TodoItem(BaseModel):
    content: str = Field(description="What the task is — a short imperative line.")
    status: str = Field(default="pending", description="pending | in_progress | completed")


class _TodoWriteArgs(BaseModel):
    todos: list[_TodoItem] = Field(
        description="The COMPLETE task list. It replaces the previous list entirely."
    )


_ALLOWED_STATUSES = {"pending", "in_progress", "completed"}


class TodoWriteTool(BaseTool):
    """Record and update the agent's structured task list."""

    name: str = "todo_write"
    description: str = (
        "Record and update a structured task list for the current work. Send the "
        "ENTIRE list every call — it REPLACES the previous list (no partial updates, "
        "no per-item edits). Use it to plan multi-step work and show progress; mark "
        "every task being worked on in_progress, and leave no in_progress item only "
        "once all work is complete."
    )
    args_schema: type[BaseModel] = _TodoWriteArgs
    todo_store: Any = None  # optional async callable(todos: list[dict]) -> object

    class Config:
        arbitrary_types_allowed = True

    def _run(self, todos: list[dict[str, Any]], **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(todos=todos, **kwargs))

    async def _arun(self, todos: list[dict[str, Any]], **kwargs: Any) -> str:
        normalized = self._normalize(todos)
        try:
            if self.todo_store is not None:
                result = self.todo_store(normalized)
                if inspect.isawaitable(result):
                    result = await result
                if result is not None:
                    normalized = list(result)
            return json.dumps({"todos": normalized}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @staticmethod
    def _normalize(todos: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in todos or []:
            # With an ``args_schema`` LangChain hands us validated model
            # instances; without one (or via direct calls) items are plain dicts.
            if isinstance(item, dict):
                content = item.get("content")
                status = item.get("status")
            else:
                content = getattr(item, "content", None)
                status = getattr(item, "status", None)
            content = str(content or "").strip()
            status = str(status or "pending").strip()
            if status not in _ALLOWED_STATUSES:
                status = "pending"
            if content:
                normalized.append({"content": content, "status": status})
        return normalized
