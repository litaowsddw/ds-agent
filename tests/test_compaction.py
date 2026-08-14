"""Structured session compaction."""

import pytest

from packages.runtime.compaction import CompactionManager


def _messages(count: int, chars: int = 100) -> list[dict]:
    return [{"role": "user", "content": "x" * chars} for _ in range(count)]


@pytest.mark.asyncio
async def test_compaction_not_needed_under_threshold() -> None:
    async def summarize(messages: list[dict]) -> str:
        return "unused"

    manager = CompactionManager(summarize, threshold_tokens=1000, keep_tail=2)
    messages = _messages(2)  # 2 * 25 = 50 tokens < 1000
    plan = await manager.compact(messages)

    assert plan.should_compact is False
    assert plan.compacted_messages == 0
    assert plan.recent_messages == messages


@pytest.mark.asyncio
async def test_compaction_summarizes_head_and_keeps_tail() -> None:
    seen: list[int] = []

    async def summarize(messages: list[dict]) -> str:
        seen.append(len(messages))
        return "compacted summary"

    manager = CompactionManager(summarize, threshold_tokens=100, keep_tail=2)
    messages = _messages(10)  # 250 tokens > 100
    plan = await manager.compact(messages)

    assert plan.should_compact is True
    assert plan.summary == "compacted summary"
    assert plan.compacted_messages == 8
    assert plan.recent_messages == messages[-2:]
    assert seen == [8]  # only the head went to the summarizer
