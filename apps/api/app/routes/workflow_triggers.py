"""Managed public webhook entrypoints for immutable Workflow versions."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Annotated, Any

from app.core.auth import AuthenticatedUser, require_org
from app.core.metrics import record_rate_limit
from app.database import get_db_session
from app.domain.identity import new_id
from app.gateway.rate_limiter import RateLimitExceeded, rate_limiter
from app.models.workflow_trigger import WorkflowWebhookTriggerModel
from app.schemas.workflow_trigger import (
    WorkflowWebhookInvocationResponse,
    WorkflowWebhookTriggerCreatedResponse,
    WorkflowWebhookTriggerCreateRequest,
    WorkflowWebhookTriggerResponse,
)
from app.services.db.identity_db import audit_log_db, membership_db
from app.services.db.workflow_db import workflow_db, workflow_run_db, workflow_version_db
from app.services.db.workflow_trigger_db import (
    workflow_webhook_delivery_db,
    workflow_webhook_trigger_db,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
public_router = APIRouter()

_MAX_WEBHOOK_REQUEST_BYTES = 128 * 1024
_WEBHOOK_RATE_LIMIT_CAPACITY = 60
_WEBHOOK_RATE_LIMIT_REFILL_PER_SECOND = 1.0


def _require_server_authenticated_identity(auth: AuthenticatedUser) -> None:
    """Webhooks change production behavior, so dev query fallback is not enough."""

    if not auth.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token or service API key required",
        )


async def _require_trigger_operator(
    session: AsyncSession, *, auth: AuthenticatedUser, org_id: str
) -> None:
    _require_server_authenticated_identity(auth)
    require_org(auth, org_id)
    await membership_db.assert_org_access(
        session, user_id=auth.user_id, org_id=org_id, required_role="developer"
    )


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _idempotency_key_hash(idempotency_key: str) -> str:
    return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


def _validate_idempotency_key(value: str | None) -> str:
    key = (value or "").strip()
    if not 8 <= len(key) <= 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must be 8 to 200 characters",
        )
    if any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key contains unsupported characters",
        )
    return key


async def _read_json_payload(request: Request) -> tuple[dict[str, Any], int]:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_WEBHOOK_REQUEST_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Webhook payload exceeds the 128 KiB limit",
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc

    raw_body = await request.body()
    if len(raw_body) > _MAX_WEBHOOK_REQUEST_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload exceeds the 128 KiB limit",
        )
    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Webhook payload must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Webhook payload must be a JSON object")
    return payload, len(raw_body)


@router.post(
    "",
    response_model=WorkflowWebhookTriggerCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook_trigger(
    request: WorkflowWebhookTriggerCreateRequest,
    auth: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkflowWebhookTriggerCreatedResponse:
    """Create one secret-protected trigger for an immutable Workflow version.

    The secret is generated server-side and only appears in this one response.
    It is never written to audit logs or the database in plaintext.
    """

    try:
        version = await workflow_version_db.get_by_id_required(
            session, request.version_id, "version_id"
        )
        workflow = await workflow_db.get_workflow_required(session, version.workflow_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow version not found",
        ) from exc
    try:
        await _require_trigger_operator(session, auth=auth, org_id=workflow.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc

    try:
        existing = await workflow_webhook_trigger_db.get_by_version(session, version.version_id)
        if existing is not None:
            raise ValueError("This published workflow version already has a webhook trigger")

        secret = secrets.token_urlsafe(32)
        trigger = await workflow_webhook_trigger_db.create_trigger(
            session,
            trigger_id=new_id("wht"),
            workflow_id=workflow.workflow_id,
            version_id=version.version_id,
            org_id=workflow.org_id,
            secret_hash=_secret_hash(secret),
            created_by=auth.user_id,
        )
        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=workflow.org_id,
            actor_user_id=auth.user_id,
            action="workflow.webhook.created",
            resource_type="workflow_webhook_trigger",
            resource_id=trigger.trigger_id,
            detail={"workflow_id": workflow.workflow_id, "version_id": version.version_id},
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Webhook trigger already exists",
        ) from exc

    return _to_created_response(trigger, secret)


@router.get("/{trigger_id}", response_model=WorkflowWebhookTriggerResponse)
async def get_webhook_trigger(
    trigger_id: str,
    auth: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkflowWebhookTriggerResponse:
    try:
        trigger = await workflow_webhook_trigger_db.get_trigger_required(session, trigger_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook trigger not found",
        ) from exc
    try:
        await _require_trigger_operator(session, auth=auth, org_id=trigger.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    return _to_response(trigger)


@router.post("/{trigger_id}/disable", response_model=WorkflowWebhookTriggerResponse)
async def disable_webhook_trigger(
    trigger_id: str,
    auth: AuthenticatedUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkflowWebhookTriggerResponse:
    try:
        trigger = await workflow_webhook_trigger_db.get_trigger_required(session, trigger_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook trigger not found",
        ) from exc
    try:
        await _require_trigger_operator(session, auth=auth, org_id=trigger.org_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    try:
        trigger = await workflow_webhook_trigger_db.disable_trigger(
            session, trigger_id=trigger_id, disabled_by=auth.user_id
        )
        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=trigger.org_id,
            actor_user_id=auth.user_id,
            action="workflow.webhook.disabled",
            resource_type="workflow_webhook_trigger",
            resource_id=trigger.trigger_id,
            detail={"workflow_id": trigger.workflow_id, "version_id": trigger.version_id},
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_response(trigger)


@public_router.post(
    "/workflows/{trigger_id}",
    response_model=WorkflowWebhookInvocationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def invoke_workflow_webhook(
    trigger_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkflowWebhookInvocationResponse:
    """Verify a third-party delivery, persist a run, then enqueue execution.

    No trigger information is exposed to callers whose id or secret is wrong.
    The body is bounded before JSON parsing and never retained in audit logs.
    """

    try:
        trigger = await workflow_webhook_trigger_db.get_trigger_required(session, trigger_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook credentials",
        ) from exc

    provided_hash = _secret_hash(x_webhook_secret or "")
    if not trigger.enabled or not hmac.compare_digest(provided_hash, trigger.secret_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook credentials",
        )

    key = _validate_idempotency_key(idempotency_key)
    key_hash = _idempotency_key_hash(key)
    payload, payload_size = await _read_json_payload(request)

    existing_delivery = await workflow_webhook_delivery_db.get_by_idempotency_key(
        session, trigger_id=trigger.trigger_id, idempotency_key_hash=key_hash
    )
    if existing_delivery is not None:
        existing_run = await workflow_run_db.get_run_required(session, existing_delivery.run_id)
        return WorkflowWebhookInvocationResponse(
            run_id=existing_run.run_id,
            status=existing_run.status,
            idempotent_replay=True,
        )

    try:
        await rate_limiter.require(
            key=f"workflow-webhook:{trigger.trigger_id}",
            capacity=_WEBHOOK_RATE_LIMIT_CAPACITY,
            refill_rate=_WEBHOOK_RATE_LIMIT_REFILL_PER_SECOND,
        )
    except RateLimitExceeded as exc:
        record_rate_limit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Webhook rate limit exceeded",
        ) from exc

    run = await workflow_run_db.create_run(
        session,
        run_id=new_id("run"),
        workflow_id=trigger.workflow_id,
        version_id=trigger.version_id,
        org_id=trigger.org_id,
        agent_id=(await workflow_db.get_workflow_required(session, trigger.workflow_id)).agent_id,
        # A trigger has no human caller.  The original authorized creator is
        # retained as the execution principal for existing Tool policy checks.
        created_by=trigger.created_by,
        input_data=payload,
    )
    try:
        await workflow_webhook_delivery_db.create_delivery(
            session,
            delivery_id=new_id("whd"),
            trigger_id=trigger.trigger_id,
            run_id=run.run_id,
            idempotency_key_hash=key_hash,
            request_size_bytes=payload_size,
        )
        await workflow_webhook_trigger_db.mark_triggered(session, trigger)
        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=trigger.org_id,
            actor_user_id="webhook",
            action="workflow.webhook.triggered",
            resource_type="workflow_webhook_trigger",
            resource_id=trigger.trigger_id,
            detail={
                "workflow_id": trigger.workflow_id,
                "version_id": trigger.version_id,
                "run_id": run.run_id,
                "payload_size_bytes": payload_size,
                "idempotency_key_fingerprint": key_hash[:12],
            },
        )
        await session.commit()
    except IntegrityError:
        # The unique receipt gives concurrent retries the same run id without
        # ever logging or returning the original idempotency key.
        await session.rollback()
        existing_delivery = await workflow_webhook_delivery_db.get_by_idempotency_key(
            session, trigger_id=trigger.trigger_id, idempotency_key_hash=key_hash
        )
        if existing_delivery is None:
            raise HTTPException(
                status_code=409, detail="Webhook delivery conflicted; retry safely"
            ) from None
        existing_run = await workflow_run_db.get_run_required(session, existing_delivery.run_id)
        return WorkflowWebhookInvocationResponse(
            run_id=existing_run.run_id,
            status=existing_run.status,
            idempotent_replay=True,
        )

    # The normal Workflow API uses Celery for durable asynchronous execution.
    # Do not report acceptance when the queue cannot receive the run.
    try:
        from apps.api.app.routes.workflow_runs import _submit_async_run

        await _submit_async_run(run)
    except ValueError as exc:
        await workflow_run_db.update_run_status(
            session, run.run_id, "failed", error_message="Webhook queue unavailable"
        )
        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=trigger.org_id,
            actor_user_id="webhook",
            action="workflow.webhook.dispatch_failed",
            resource_type="workflow_webhook_trigger",
            resource_id=trigger.trigger_id,
            detail={"run_id": run.run_id},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Workflow queue unavailable",
        ) from exc

    return WorkflowWebhookInvocationResponse(run_id=run.run_id, status=run.status)


def _to_response(trigger: WorkflowWebhookTriggerModel) -> WorkflowWebhookTriggerResponse:
    return WorkflowWebhookTriggerResponse(
        trigger_id=trigger.trigger_id,
        workflow_id=trigger.workflow_id,
        version_id=trigger.version_id,
        org_id=trigger.org_id,
        enabled=trigger.enabled,
        invoke_path=f"/webhooks/workflows/{trigger.trigger_id}",
        created_by=trigger.created_by,
        disabled_by=trigger.disabled_by,
        disabled_at=trigger.disabled_at,
        last_triggered_at=trigger.last_triggered_at,
        created_at=trigger.created_at,
    )


def _to_created_response(
    trigger: WorkflowWebhookTriggerModel, secret: str
) -> WorkflowWebhookTriggerCreatedResponse:
    return WorkflowWebhookTriggerCreatedResponse(
        **_to_response(trigger).model_dump(), secret=secret
    )
