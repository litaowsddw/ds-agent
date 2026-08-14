"""Ask-user tool wrapper."""

import json

import pytest

from packages.runtime.tools.ask_user_tool import AskUserTool


@pytest.mark.asyncio
async def test_ask_user_normalizes_questions_and_returns_answers() -> None:
    async def accessor(questions: list[dict]) -> dict[str, str]:
        return {q["id"]: f"answer-{q['id']}" for q in questions}

    tool = AskUserTool(ask_user_accessor=accessor)
    result = json.loads(await tool.ainvoke({"questions": [
        {"id": "q1", "question": "what?", "options": ["a", "b"]},
    ]}))

    assert result == {"q1": "answer-q1"}


@pytest.mark.asyncio
async def test_ask_user_fails_honestly_without_accessor() -> None:
    result = json.loads(await AskUserTool().ainvoke({"questions": [{"id": "q1", "question": "w"}]}))
    assert result == {"error": "Ask-user accessor is not configured"}
