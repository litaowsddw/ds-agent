"""Authenticated direct LLM Gateway routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.core.security import decrypt_api_key
from app.database import get_db_session
from app.gateway.llm import (
    GatewayProviderError,
    LLMCallLog,
    LLMCallRequest,
    LLMGateway,
    OpenAICompatibleProvider,
    RateLimitExceeded,
    llm_gateway,
)
from app.schemas.gateway import LLMCallLogResponse, LLMGenerateRequest, LLMGenerateResponse
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import model_provider_db
from app.services.metering import SessionUsageRecorder, UsageContext

router = APIRouter()


def _require_server_authenticated_identity(auth: AuthenticatedUser) -> None:
    """Reject the development-only query-string actor fallback for accounting."""

    if not auth.email:
        raise HTTPException(status_code=401, detail="Bearer token or service API key required")


@router.post("/llm/generate", response_model=LLMGenerateResponse)
async def generate_llm(
    request: LLMGenerateRequest,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> LLMGenerateResponse:
    """Call a provider in the caller's authenticated organization context."""

    _require_server_authenticated_identity(auth)
    org_id = auth.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Select an organization before calling Gateway")
    try:
        await membership_db.assert_org_access(session, user_id=auth.user_id, org_id=org_id)
        provider_config = await model_provider_db.get_by_key(session, org_id, request.provider)
        if provider_config is None or not provider_config.is_enabled:
            raise GatewayProviderError(f"No enabled model provider: {request.provider}")

        api_key = (
            decrypt_api_key(provider_config.api_key_encrypted)
            if provider_config.api_key_encrypted
            else ""
        )
        gateway = LLMGateway(
            providers={
                provider_config.provider_key: OpenAICompatibleProvider(
                    base_url=provider_config.base_url,
                    api_key=api_key,
                    provider_key=provider_config.provider_key,
                )
            },
            limiter=llm_gateway.limiter,
            usage_recorder=SessionUsageRecorder(session),
        )
        response = await gateway.generate(
            LLMCallRequest(
                provider=request.provider,
                model=request.model,
                prompt=request.prompt,
                parameters=request.parameters,
                metadata=UsageContext(
                    org_id=org_id,
                    actor_user_id=auth.user_id,
                    source="gateway_api",
                    api_name="chat.completions",
                ).as_metadata(),
            )
        )
        llm_gateway.call_logs.extend(gateway.list_logs())
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        await session.commit()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except GatewayProviderError as exc:
        # The terminal attempt is a trusted metering fact even if the provider fails.
        await session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return LLMGenerateResponse(
        text=response.text,
        provider=response.provider,
        model=response.model,
        usage=response.usage,
    )


@router.get("/llm/logs", response_model=list[LLMCallLogResponse])
async def list_llm_logs() -> list[LLMCallLogResponse]:
    """Return temporary in-process diagnostic logs."""

    return [_to_log_response(log) for log in llm_gateway.list_logs()]


def _to_log_response(log: LLMCallLog) -> LLMCallLogResponse:
    return LLMCallLogResponse(
        call_id=log.call_id,
        provider=log.provider,
        model=log.model,
        prompt_preview=log.prompt_preview,
        prefix_hash=log.prefix_hash,
        status=log.status,
        usage=log.usage,
        error_message=log.error_message,
        metadata=log.metadata,
    )
