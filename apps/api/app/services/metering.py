"""Gateway-side normalization of provider-reported LLM usage.

This module intentionally keeps provider facts nullable. It creates no billing
entries and never derives usage from prompt text or streamed characters.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Mapping, Protocol

from apps.api.app.services.db.metering_db import UsageEventInput


@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cache_read_input_tokens: int | None
    cache_miss_input_tokens: int | None
    usage_status: str
    cache_usage_status: str


@dataclass(frozen=True, slots=True)
class UsageTerminalOutcome:
    """One Gateway terminal outcome, without prompt text or provider secrets."""

    dispatch_status: str
    usage: NormalizedUsage
    completed_at: datetime
    error_category: str | None = None
    error_code: str | None = None

    @property
    def input_tokens(self) -> int | None:
        return self.usage.input_tokens

    @property
    def output_tokens(self) -> int | None:
        return self.usage.output_tokens

    @property
    def total_tokens(self) -> int | None:
        return self.usage.total_tokens

    @property
    def cache_read_input_tokens(self) -> int | None:
        return self.usage.cache_read_input_tokens

    @property
    def cache_miss_input_tokens(self) -> int | None:
        return self.usage.cache_miss_input_tokens

    @property
    def usage_status(self) -> str:
        return self.usage.usage_status

    @property
    def cache_usage_status(self) -> str:
        return self.usage.cache_usage_status


class UsageRecorder(Protocol):
    """Receives the start and exactly one terminal fact for a Gateway call."""

    async def record_started(self, context: UsageEventInput) -> None:
        """Register a call attempt using the Task 1 storage DTO."""

    async def record_terminal(
        self, call_id: str, outcome: UsageTerminalOutcome
    ) -> None:
        """Register the single terminal outcome for a call."""


def normalize_usage(raw: Mapping[str, object] | None) -> NormalizedUsage:
    """Normalize provider usage without converting unavailable data to zero."""

    raw = raw or {}
    input_tokens = _integer_or_none(_first_present(raw, "prompt_tokens", "input_tokens"))
    output_tokens = _integer_or_none(
        _first_present(raw, "completion_tokens", "output_tokens")
    )
    total_tokens = _integer_or_none(raw.get("total_tokens"))
    cache_value = _first_present(raw, "prompt_cache_hit_tokens", "cached_tokens")
    if cache_value is None:
        details = raw.get("prompt_tokens_details")
        if isinstance(details, Mapping):
            cache_value = details.get("cached_tokens")
    cache_read = _integer_or_none(cache_value)
    cache_miss = (
        input_tokens - cache_read
        if input_tokens is not None and cache_read is not None
        else None
    )
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return NormalizedUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cache_read_input_tokens=cache_read,
        cache_miss_input_tokens=cache_miss,
        usage_status=(
            "provider_final"
            if input_tokens is not None or output_tokens is not None or total_tokens is not None
            else "unavailable"
        ),
        cache_usage_status="known" if cache_read is not None else "unknown",
    )


def unavailable_usage() -> NormalizedUsage:
    return normalize_usage(None)


def usage_event_for_terminal(
    context: UsageEventInput, outcome: UsageTerminalOutcome
) -> UsageEventInput:
    """Materialize the Task 1 DTO from a terminal outcome for durable storage."""

    return replace(
        context,
        dispatch_status=outcome.dispatch_status,
        usage_status=outcome.usage_status,
        completed_at=outcome.completed_at,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        total_tokens=outcome.total_tokens,
        cache_usage_status=outcome.cache_usage_status,
        cache_read_input_tokens=outcome.cache_read_input_tokens,
        error_category=outcome.error_category,
        error_code=outcome.error_code,
    )


def _first_present(raw: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _integer_or_none(value: object | None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
