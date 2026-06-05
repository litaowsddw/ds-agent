"""Hermes-style three-layer memory helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


class MessageLike(Protocol):
    role: str
    content: str
    sequence: int
    estimated_tokens: int


class MemoryLike(Protocol):
    memory_type: str
    summary: str
    content: str
    confidence: float


@dataclass(frozen=True)
class ThreeLayerMemoryContext:
    recent_context: str
    compact_summary: str
    long_term_context: str
    total_estimated_tokens: int
    should_compact: bool

    @property
    def prompt_context(self) -> str:
        return "\n\n".join(
            [
                "[Hermes Memory Layer 1: Recent Turns]",
                self.recent_context or "No recent turns.",
                "[Hermes Memory Layer 2: Compressed Session Summary]",
                self.compact_summary or "No compressed summary yet.",
                "[Hermes Memory Layer 3: Long-Term Memory and Rules]",
                self.long_term_context or "No recalled long-term memory.",
            ]
        )


def build_three_layer_memory_context(
    *,
    recent_messages: Iterable[MessageLike],
    compact_summary: str,
    memories: Iterable[MemoryLike],
    token_threshold: int,
) -> ThreeLayerMemoryContext:
    recent_list = list(recent_messages)
    memory_list = list(memories)
    recent_context = format_recent_messages(recent_list)
    long_term_context = format_long_term_memories(memory_list)
    total_tokens = (
        estimate_tokens(recent_context)
        + estimate_tokens(compact_summary)
        + estimate_tokens(long_term_context)
    )
    return ThreeLayerMemoryContext(
        recent_context=recent_context,
        compact_summary=compact_summary,
        long_term_context=long_term_context,
        total_estimated_tokens=total_tokens,
        should_compact=total_tokens >= token_threshold,
    )


def format_recent_messages(messages: Iterable[MessageLike]) -> str:
    lines = []
    for message in sorted(messages, key=lambda item: int(item.sequence)):
        lines.append(f"{message.sequence}. {message.role}: {message.content}")
    return "\n".join(lines)


def format_long_term_memories(memories: Iterable[MemoryLike]) -> str:
    lines = []
    for memory in memories:
        label = str(memory.memory_type or "memory")
        summary = str(memory.summary or memory.content or "")
        confidence = getattr(memory, "confidence", "")
        lines.append(f"- [{label}] {summary} (confidence={confidence})")
    return "\n".join(lines)


def build_compaction_prompt(
    *,
    existing_summary: str,
    messages_text: str,
) -> str:
    return f"""Compress the conversation into a durable session memory summary.

Rules:
- Preserve user goals, constraints, decisions, tool/API outcomes, IDs only when useful, and unresolved tasks.
- Drop greetings, repeated wording, and low-value chatter.
- Keep it concise but enough for future turns to continue correctly.
- Output plain text only.

[Existing compressed summary]
{existing_summary or "None"}

[Recent messages to merge]
{messages_text}
"""


def build_memory_extraction_candidate(user_input: str) -> tuple[str, str] | None:
    """Heuristic long-term memory candidate extraction.

    This is intentionally conservative. It only records explicit user preferences,
    rules, or durable facts instead of inferring private facts from ordinary chat.
    """

    text = " ".join(user_input.split())
    if not text:
        return None
    triggers = (
        "记住",
        "请记住",
        "以后",
        "偏好",
        "规则",
        "不要",
        "默认",
        "长期",
        "remember",
        "preference",
        "always",
        "never",
    )
    if not any(trigger.lower() in text.lower() for trigger in triggers):
        return None
    memory_type = "rule" if any(trigger in text for trigger in ("规则", "不要", "默认", "always", "never")) else "preference"
    return memory_type, text[:1000]


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)
