"""Redacted contracts for organization usage insights."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


UsageGroupBy = Literal["api", "provider", "model", "agent", "workflow", "source"]
UsageGranularity = Literal["hour", "day"]


class UsageAggregateResponse(BaseModel):
    """One safe, organization-scoped aggregate bucket."""

    bucket_start: datetime | None = None
    api_name: str | None = None
    provider_key: str | None = None
    model: str | None = None
    agent_id: str | None = None
    workflow_id: str | None = None
    source: str | None = None
    call_count: int
    unknown_usage_calls: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None


class UsageSummaryResponse(BaseModel):
    """Read-only aggregate usage response; no billing amounts are calculated."""

    org_id: str
    group_by: UsageGroupBy
    granularity: UsageGranularity
    created_at_from: datetime
    created_at_to: datetime
    groups: list[UsageAggregateResponse] = Field(default_factory=list)


class PrefixUsageAggregateResponse(BaseModel):
    """Bucketed prefix-cache diagnostics without a prefix value or hash."""

    bucket_start: datetime | None = None
    prefix_cache_status: str | None = None
    prefix_length_bucket: str | None = None
    call_count: int
    unknown_usage_calls: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_input_tokens: int | None = None


class PrefixUsageResponse(BaseModel):
    org_id: str
    created_at_from: datetime
    created_at_to: datetime
    groups: list[PrefixUsageAggregateResponse] = Field(default_factory=list)


class UsageEventResponse(BaseModel):
    """Explicit allow-list for a single safe metering event."""

    event_id: str
    gateway_call_id: str
    created_at: datetime
    source: str
    api_name: str
    provider_key: str
    model: str
    actor_user_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None
    workflow_version_id: str | None = None
    workflow_run_id: str | None = None
    workflow_node_id: str | None = None
    dispatch_status: str
    usage_status: str
    cache_usage_status: str
    prefix_cache_status: str | None = None
    prefix_length_bucket: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    latency_ms: int | None = None
    error_category: str | None = None
    error_code: str | None = None
    error_http_status: int | None = None
    error_retryable: bool | None = None


class UsageEventsResponse(BaseModel):
    org_id: str
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None
    events: list[UsageEventResponse] = Field(default_factory=list)
    offset: int
    limit: int
    has_more: bool = False
