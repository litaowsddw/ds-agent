"""Read-only organization-scoped usage endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.database import get_db_session
from app.schemas.metering import (
    PrefixUsageAggregateResponse,
    PrefixUsageResponse,
    UsageAggregateResponse,
    UsageEventResponse,
    UsageEventsResponse,
    UsageGranularity,
    UsageGroupBy,
    UsageSummaryResponse,
)
from app.services.db.identity_db import membership_db
from app.services.db.metering_db import UsageFilters, metering_db
from app.services.rbac import Permission, rbac_service


router = APIRouter()
_DEFAULT_WINDOW = timedelta(days=7)
_MAX_WINDOW = timedelta(days=31)
_GROUP_BY_FIELDS = {
    "api": "api_name",
    "provider": "provider_key",
    "model": "model",
    "agent": "agent_id",
    "workflow": "workflow_id",
    "source": "source",
}


class MeteringQuery:
    """Validated query values shared by every usage endpoint."""

    def __init__(
        self,
        org_id: Annotated[str | None, Query(min_length=1)] = None,
        created_at_from: Annotated[datetime | None, Query(alias="from")] = None,
        created_at_to: Annotated[datetime | None, Query(alias="to")] = None,
        source: Annotated[str | None, Query()] = None,
        api_name: Annotated[str | None, Query(alias="api")] = None,
        provider_key: Annotated[str | None, Query(alias="provider")] = None,
        model: Annotated[str | None, Query()] = None,
        agent_id: Annotated[str | None, Query(alias="agent")] = None,
        workflow_id: Annotated[str | None, Query(alias="workflow")] = None,
        group_by: UsageGroupBy = "model",
        granularity: UsageGranularity = "day",
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> None:
        end = _as_utc(created_at_to) if created_at_to else datetime.now(UTC)
        start = _as_utc(created_at_from) if created_at_from else end - _DEFAULT_WINDOW
        if end <= start:
            raise HTTPException(status_code=422, detail="'to' must be after 'from'")
        if end - start > _MAX_WINDOW:
            raise HTTPException(status_code=422, detail="usage query range exceeds 31 days")
        self.requested_org_id = org_id
        self.created_at_from = start
        self.created_at_to = end
        self.group_by = group_by
        self.granularity = granularity
        self.offset = offset
        self.limit = limit
        self._filter_values = dict(
            created_at_from=start,
            created_at_to=end,
            source=source,
            api_name=api_name,
            provider_key=provider_key,
            model=model,
            agent_id=agent_id,
            workflow_id=workflow_id,
        )

    def filters_for_org(self, org_id: str) -> UsageFilters:
        """Construct filters only after the tenant is server-authenticated."""
        return UsageFilters(org_id=org_id, **self._filter_values)


async def _authorize_billing_access(
    query: MeteringQuery,
    auth: AuthenticatedUser,
    session: AsyncSession,
) -> str:
    """Require both membership and the read-only billing permission."""
    if not auth.org_id:
        raise HTTPException(status_code=403, detail="authenticated organization context required")
    if query.requested_org_id and query.requested_org_id != auth.org_id:
        raise HTTPException(status_code=403, detail="organization scope does not match token")
    try:
        membership = await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=auth.org_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="organization access denied") from exc
    if not rbac_service.has_permission(membership, Permission.ORGANIZATION_BILLING):
        raise HTTPException(status_code=403, detail="billing usage access denied")
    return auth.org_id


@router.get(
    "/usage/summary",
    response_model=UsageSummaryResponse,
    response_model_exclude_none=True,
)
async def usage_summary(
    query: Annotated[MeteringQuery, Depends()],
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> UsageSummaryResponse:
    """Aggregate provider-reported usage for one authorized organization."""
    org_id = await _authorize_billing_access(query, auth, session)
    db_group_by = _GROUP_BY_FIELDS[query.group_by]
    rows = await metering_db.aggregate_usage(
        session, query.filters_for_org(org_id), db_group_by, query.granularity
    )
    return UsageSummaryResponse(
        org_id=org_id,
        group_by=query.group_by,
        granularity=query.granularity,
        created_at_from=query.created_at_from,
        created_at_to=query.created_at_to,
        groups=[_aggregate_response(row) for row in rows],
    )


@router.get(
    "/usage/by-prefix",
    response_model=PrefixUsageResponse,
    response_model_exclude_none=True,
)
async def usage_by_prefix(
    query: Annotated[MeteringQuery, Depends()],
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> PrefixUsageResponse:
    """Return only bucketed prefix-cache diagnostics, never a prefix/hash."""
    org_id = await _authorize_billing_access(query, auth, session)
    rows = await metering_db.aggregate_prefix_usage(
        session, query.filters_for_org(org_id), query.granularity
    )
    return PrefixUsageResponse(
        org_id=org_id,
        created_at_from=query.created_at_from,
        created_at_to=query.created_at_to,
        groups=[PrefixUsageAggregateResponse(**row) for row in rows],
    )


@router.get(
    "/usage/events",
    response_model=UsageEventsResponse,
    response_model_exclude_none=True,
)
async def usage_events(
    query: Annotated[MeteringQuery, Depends()],
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> UsageEventsResponse:
    """Return a paginated, explicit allow-list of safe event fields."""
    org_id = await _authorize_billing_access(query, auth, session)
    events = await metering_db.list_usage_events(
        session, query.filters_for_org(org_id), offset=query.offset, limit=query.limit
    )
    return UsageEventsResponse(
        org_id=org_id,
        created_at_from=query.created_at_from,
        created_at_to=query.created_at_to,
        events=[_event_response(event) for event in events],
        offset=query.offset,
        limit=query.limit,
    )


def _aggregate_response(row: object) -> UsageAggregateResponse:
    return UsageAggregateResponse(
        bucket_start=getattr(row, "bucket_start"),
        api_name=getattr(row, "api_name"),
        provider_key=getattr(row, "provider_key"),
        model=getattr(row, "model"),
        agent_id=getattr(row, "agent_id"),
        workflow_id=getattr(row, "workflow_id"),
        source=getattr(row, "source"),
        call_count=getattr(row, "call_count"),
        unknown_usage_calls=getattr(row, "unknown_usage_calls"),
        input_tokens=getattr(row, "input_tokens"),
        output_tokens=getattr(row, "output_tokens"),
        total_tokens=getattr(row, "total_tokens"),
        reasoning_tokens=getattr(row, "reasoning_tokens"),
        cache_read_input_tokens=getattr(row, "cache_read_input_tokens"),
        cache_write_input_tokens=getattr(row, "cache_write_input_tokens"),
    )


def _event_response(event: object) -> UsageEventResponse:
    dispatched_at = getattr(event, "dispatched_at")
    completed_at = getattr(event, "completed_at")
    latency_ms = None
    if dispatched_at is not None and completed_at is not None:
        latency_ms = max(0, int((completed_at - dispatched_at).total_seconds() * 1000))
    return UsageEventResponse(
        event_id=getattr(event, "event_id"),
        gateway_call_id=getattr(event, "gateway_call_id"),
        created_at=getattr(event, "created_at"),
        source=getattr(event, "source"),
        api_name=getattr(event, "api_name"),
        provider_key=getattr(event, "provider_key"),
        model=getattr(event, "model"),
        actor_user_id=getattr(event, "actor_user_id"),
        agent_id=getattr(event, "agent_id"),
        session_id=getattr(event, "session_id"),
        workflow_id=getattr(event, "workflow_id"),
        workflow_version_id=getattr(event, "workflow_version_id"),
        workflow_run_id=getattr(event, "workflow_run_id"),
        workflow_node_id=getattr(event, "workflow_node_id"),
        dispatch_status=getattr(event, "dispatch_status"),
        usage_status=getattr(event, "usage_status"),
        cache_usage_status=getattr(event, "cache_usage_status"),
        prefix_cache_status=getattr(event, "prefix_cache_status"),
        prefix_length_bucket=getattr(event, "prefix_length_bucket"),
        input_tokens=getattr(event, "input_tokens"),
        output_tokens=getattr(event, "output_tokens"),
        total_tokens=getattr(event, "total_tokens"),
        reasoning_tokens=getattr(event, "reasoning_tokens"),
        cache_read_input_tokens=getattr(event, "cache_read_input_tokens"),
        cache_write_input_tokens=getattr(event, "cache_write_input_tokens"),
        latency_ms=latency_ms,
        error_category=getattr(event, "error_category"),
        error_code=getattr(event, "error_code"),
        error_http_status=getattr(event, "error_http_status"),
        error_retryable=getattr(event, "error_retryable"),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
