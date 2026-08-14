"""Ask-user tool → LangChain BaseTool wrapper.

Models DeepSeek Harness ``dsh-tool-ask-user``: present one or more questions
(optionally with choices) and receive the user's answers.  The answer channel
is injected by the runtime; an unconfigured tool fails honestly instead of
fabricating an answer.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class _Question(BaseModel):
    id: str = Field(description="Stable id echoed back with the answer.")
    question: str = Field(description="The specific question to ask the user.")
    header: str | None = Field(default=None, description="Optional short heading.")
    options: list[str] | None = Field(default=None, description="Optional choices.")
    multi_select: bool = Field(default=False, description="Allow more than one choice.")


class _AskUserArgs(BaseModel):
    questions: list[_Question] = Field(description="One or more questions for the user.")


def _normalize_questions(questions: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in questions or []:
        if isinstance(item, dict):
            data = item
        else:
            data = {
                "id": getattr(item, "id", None),
                "question": getattr(item, "question", None),
                "header": getattr(item, "header", None),
                "options": getattr(item, "options", None),
                "multi_select": getattr(item, "multi_select", False),
            }
        if data.get("id") and data.get("question"):
            normalized.append(
                {
                    "id": str(data["id"]),
                    "question": str(data["question"]),
                    "header": data.get("header"),
                    "options": data.get("options"),
                    "multi_select": bool(data.get("multi_select", False)),
                }
            )
    return normalized


class AskUserTool(BaseTool):
    """Ask the user one or more questions and return their answers."""

    name: str = "ask_user"
    description: str = (
        "Ask the user one or more questions when you need confirmation, a choice, "
        "or missing information before proceeding. Each question has a stable id, "
        "an optional header, optional choices, and a multi_select flag; the answer "
        "is returned keyed by id."
    )
    args_schema: type[BaseModel] = _AskUserArgs
    ask_user_accessor: Any = None  # async callable(questions=...) -> object

    class Config:
        arbitrary_types_allowed = True

    def _run(self, questions: list[dict[str, Any]], **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(questions=questions, **kwargs))

    async def _arun(self, questions: list[dict[str, Any]], **kwargs: Any) -> str:
        if not self.ask_user_accessor:
            return json.dumps({"error": "Ask-user accessor is not configured"}, ensure_ascii=False)
        try:
            normalized = _normalize_questions(questions)
            result = self.ask_user_accessor(questions=normalized)
            if inspect.isawaitable(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
