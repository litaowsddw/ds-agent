"""Utilities for streaming chat execution events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ChatTraceEvent:
    """A single event emitted during chat execution."""

    event: str
    data: dict[str, Any] = field(default_factory=dict)


def format_sse_event(event: ChatTraceEvent) -> str:
    """Serialize a chat event as a Server-Sent Events frame."""

    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event}\ndata: {payload}\n\n"
