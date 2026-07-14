"""Persistence and aggregation for immutable LLM usage events."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metering import LLMUsageEventModel


@dataclass(frozen=True)
class UsageEventInput:
    gateway_call_id: str
    org_id: str
    source: str
    api_name: str
    provider_key: str
    model: str
    dispatch_status: str
    usage_status: str
    actor_user_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None
    workflow_version_id: str | None = None
    workflow_run_id: str | None = None
    workflow_node_id: str | None = None
    provider_request_id: str | None = None
    dispatched_at: datetime | None = None
    completed_at: datetime | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_usage_status: str = "unknown"
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    prefix_cache_status: str | None = None
    prefix_length_bucket: str | None = None
    prefix_diagnostic_key_id: str | None = None
    estimated_cost_status: str | None = None
    currency: str | None = None
    estimated_input_cost: Decimal | None = None
    estimated_output_cost: Decimal | None = None
    estimated_cache_read_cost: Decimal | None = None
    estimated_cache_write_cost: Decimal | None = None
    estimated_total_cost: Decimal | None = None
    error_category: str | None = None
    error_code: str | None = None
    error_http_status: int | None = None
    error_retryable: bool | None = None


@dataclass(frozen=True)
class UsageFilters:
    org_id: str
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None
    source: str | None = None
    api_name: str | None = None
    provider_key: str | None = None
    model: str | None = None
    actor_user_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None
    workflow_run_id: str | None = None


@dataclass
class UsageAggregate:
    group_by: str
    group_value: str | None
    call_count: int
    unknown_usage_calls: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    reasoning_tokens: int | None
    cache_read_input_tokens: int | None
    cache_write_input_tokens: int | None
    model: str | None = None
    provider_key: str | None = None
    agent_id: str | None = None
    actor_user_id: str | None = None
    source: str | None = None
    api_name: str | None = None
    workflow_id: str | None = None
    workflow_run_id: str | None = None
    bucket_start: datetime | None = None


class MeteringDBService:
    """Stores first-write provider facts and calculates scoped usage totals."""

    _GROUP_COLUMNS = {
        "model": LLMUsageEventModel.model,
        "provider_key": LLMUsageEventModel.provider_key,
        "agent_id": LLMUsageEventModel.agent_id,
        "actor_user_id": LLMUsageEventModel.actor_user_id,
        "source": LLMUsageEventModel.source,
        "api_name": LLMUsageEventModel.api_name,
        "workflow_id": LLMUsageEventModel.workflow_id,
        "workflow_run_id": LLMUsageEventModel.workflow_run_id,
    }

    async def list_usage_events(
        self,
        session: AsyncSession,
        filters: UsageFilters,
        *,
        offset: int,
        limit: int,
    ) -> list[LLMUsageEventModel]:
        """List only events already bounded to the caller's organization."""
        statement = (
            select(LLMUsageEventModel)
            .where(LLMUsageEventModel.org_id == filters.org_id)
            .order_by(LLMUsageEventModel.created_at.desc(), LLMUsageEventModel.event_id.desc())
            .offset(offset)
            .limit(limit)
        )
        statement = self._apply_filters(statement, filters)
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def aggregate_prefix_usage(
        self, session: AsyncSession, filters: UsageFilters, granularity: str | None = None
    ) -> list[dict[str, int | str | None]]:
        """Aggregate bucketed prefix facts without selecting a prefix/hash value."""
        unknown_usage = case(
            (
                or_(
                    LLMUsageEventModel.input_tokens.is_(None),
                    LLMUsageEventModel.output_tokens.is_(None),
                ),
                1,
            ),
            else_=0,
        )
        columns = [
                LLMUsageEventModel.prefix_cache_status,
                LLMUsageEventModel.prefix_length_bucket,
                func.count(LLMUsageEventModel.event_id).label("call_count"),
                func.sum(unknown_usage).label("unknown_usage_calls"),
                func.sum(LLMUsageEventModel.input_tokens).label("input_tokens"),
                func.sum(LLMUsageEventModel.output_tokens).label("output_tokens"),
                func.sum(LLMUsageEventModel.total_tokens).label("total_tokens"),
                func.sum(LLMUsageEventModel.cache_read_input_tokens).label(
                    "cache_read_input_tokens"
                ),
        ]
        grouping = [
            LLMUsageEventModel.prefix_cache_status,
            LLMUsageEventModel.prefix_length_bucket,
        ]
        ordering = list(grouping)
        if granularity is not None:
            bucket_expression = self._time_bucket_expression(session, granularity).label(
                "bucket_start"
            )
            columns.insert(0, bucket_expression)
            grouping.insert(0, bucket_expression)
            ordering.insert(0, bucket_expression)
        statement = (
            select(*columns)
            .where(LLMUsageEventModel.org_id == filters.org_id)
            .group_by(*grouping)
            .order_by(*ordering)
        )
        statement = self._apply_filters(statement, filters)
        result = await session.execute(statement)
        return [self._mapping_with_bucket(dict(row)) for row in result.mappings()]

    async def record_event(
        self, session: AsyncSession, event: UsageEventInput
    ) -> LLMUsageEventModel:
        """Persist an event once; replays return the original fact unchanged."""
        existing = await self._get_by_gateway_call(session, event.org_id, event.gateway_call_id)
        if existing is not None:
            return existing

        usage_event = LLMUsageEventModel(**asdict(event))
        try:
            async with session.begin_nested():
                session.add(usage_event)
                await session.flush()
        except IntegrityError:
            existing = await self._get_by_gateway_call(session, event.org_id, event.gateway_call_id)
            if existing is None:
                raise
            return existing
        return usage_event

    async def aggregate_usage(
        self,
        session: AsyncSession,
        filters: UsageFilters,
        group_by: str,
        granularity: str | None = None,
    ) -> list[UsageAggregate]:
        """Sum known usage fields and count attempts with unavailable token usage."""
        group_column = self._GROUP_COLUMNS.get(group_by)
        if group_column is None:
            raise ValueError(f"Unsupported usage aggregation dimension: {group_by}")

        unknown_usage = case(
            (
                or_(
                    LLMUsageEventModel.input_tokens.is_(None),
                    LLMUsageEventModel.output_tokens.is_(None),
                ),
                1,
            ),
            else_=0,
        )
        columns = [
                group_column.label("group_value"),
                func.count(LLMUsageEventModel.event_id).label("call_count"),
                func.sum(unknown_usage).label("unknown_usage_calls"),
                func.sum(LLMUsageEventModel.input_tokens).label("input_tokens"),
                func.sum(LLMUsageEventModel.output_tokens).label("output_tokens"),
                func.sum(LLMUsageEventModel.total_tokens).label("total_tokens"),
                func.sum(LLMUsageEventModel.reasoning_tokens).label("reasoning_tokens"),
                func.sum(LLMUsageEventModel.cache_read_input_tokens).label(
                    "cache_read_input_tokens"
                ),
                func.sum(LLMUsageEventModel.cache_write_input_tokens).label(
                    "cache_write_input_tokens"
                ),
        ]
        grouping = [group_column]
        ordering = [group_column]
        if granularity is not None:
            bucket_expression = self._time_bucket_expression(session, granularity).label(
                "bucket_start"
            )
            columns.insert(0, bucket_expression)
            grouping.insert(0, bucket_expression)
            ordering.insert(0, bucket_expression)
        statement = (
            select(*columns)
            .where(LLMUsageEventModel.org_id == filters.org_id)
            .group_by(*grouping)
            .order_by(*ordering)
        )
        statement = self._apply_filters(statement, filters)
        result = await session.execute(statement)
        aggregates: list[UsageAggregate] = []
        for row in result.mappings():
            aggregate = UsageAggregate(
                group_by=group_by,
                group_value=row["group_value"],
                call_count=int(row["call_count"]),
                unknown_usage_calls=int(row["unknown_usage_calls"] or 0),
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                total_tokens=row["total_tokens"],
                reasoning_tokens=row["reasoning_tokens"],
                cache_read_input_tokens=row["cache_read_input_tokens"],
                cache_write_input_tokens=row["cache_write_input_tokens"],
                bucket_start=self._bucket_datetime(row.get("bucket_start")),
            )
            setattr(aggregate, group_by, row["group_value"])
            aggregates.append(aggregate)
        return aggregates

    @staticmethod
    def _time_bucket_expression(session: AsyncSession, granularity: str):
        if granularity not in {"hour", "day"}:
            raise ValueError(f"Unsupported usage granularity: {granularity}")
        pattern = "%Y-%m-%d %H:00:00" if granularity == "hour" else "%Y-%m-%d 00:00:00"
        dialect = session.get_bind().dialect.name
        if dialect == "sqlite":
            return func.strftime(pattern, LLMUsageEventModel.created_at)
        if dialect == "mysql":
            return func.date_format(LLMUsageEventModel.created_at, pattern)
        raise ValueError(f"Unsupported metering database dialect: {dialect}")

    @staticmethod
    def _bucket_datetime(value: object | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)

    @classmethod
    def _mapping_with_bucket(cls, row: dict[str, object]) -> dict[str, object]:
        if "bucket_start" in row:
            row["bucket_start"] = cls._bucket_datetime(row["bucket_start"])
        return row

    @staticmethod
    async def _get_by_gateway_call(
        session: AsyncSession, org_id: str, gateway_call_id: str
    ) -> LLMUsageEventModel | None:
        result = await session.execute(
            select(LLMUsageEventModel).where(
                LLMUsageEventModel.org_id == org_id,
                LLMUsageEventModel.gateway_call_id == gateway_call_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _apply_filters(statement, filters: UsageFilters):
        for field in (
            "source",
            "api_name",
            "provider_key",
            "model",
            "actor_user_id",
            "agent_id",
            "session_id",
            "workflow_id",
            "workflow_run_id",
        ):
            value = getattr(filters, field)
            if value is not None:
                statement = statement.where(getattr(LLMUsageEventModel, field) == value)
        if filters.created_at_from is not None:
            statement = statement.where(LLMUsageEventModel.created_at >= filters.created_at_from)
        if filters.created_at_to is not None:
            statement = statement.where(LLMUsageEventModel.created_at < filters.created_at_to)
        return statement


metering_db = MeteringDBService()
