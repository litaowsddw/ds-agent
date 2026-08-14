"""Structured session compaction — models DeepSeek Harness ``dsh-compaction-basic``.

A ``CompactionManager`` decides when a conversation exceeds a token budget and
compacts the old head into a summary (via an injected LLM ``summarize``), while
preserving the recent tail.  The result feeds the session-summary slot of
``PromptContextCompiler.compile_messages``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True, slots=True)
class CompactionPlan:
    """The outcome of one compaction pass."""

    should_compact: bool
    summary: str
    recent_messages: list[dict[str, Any]]
    compacted_messages: int


SummarizeFn = Callable[[list[dict[str, Any]]], Awaitable[str] | str]


class CompactionManager:
    """Decide and perform structured compaction over a message sequence."""

    def __init__(
        self,
        summarize: SummarizeFn,
        *,
        threshold_tokens: int = 8_000,
        keep_tail: int = 6,
        estimate_tokens: Callable[[str], int] | None = None,
    ) -> None:
        self.summarize = summarize
        self.threshold_tokens = threshold_tokens
        self.keep_tail = keep_tail
        self._estimate = estimate_tokens or (lambda text: max(1, len(text) // 4))

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        return sum(self._estimate(str(message.get("content", ""))) for message in messages)

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        return self.estimate_tokens(messages) > self.threshold_tokens

    async def compact(self, messages: list[dict[str, Any]]) -> CompactionPlan:
        """Compact the head into a summary, keeping the recent tail intact."""

        if not self.should_compact(messages):
            return CompactionPlan(False, "", list(messages), 0)

        keep_tail = max(0, int(self.keep_tail))
        head = messages[:-keep_tail] if keep_tail else list(messages)
        tail = list(messages[-keep_tail:]) if keep_tail else []
        summary = await self.summarize(head)
        return CompactionPlan(
            should_compact=True,
            summary=str(summary or "").strip(),
            recent_messages=tail,
            compacted_messages=len(head),
        )
