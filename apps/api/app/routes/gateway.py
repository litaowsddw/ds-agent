"""Gateway API。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.database import get_db_session
from app.services.db.runtime_db import model_provider_db
from app.gateway.llm import (
    GatewayProviderError,
    LLMCallLog,
    LLMCallRequest,
    LLMGateway,
    OpenAICompatibleProvider,
    llm_gateway,
)
from apps.api.app.schemas.gateway import (
    LLMCallLogResponse,
    LLMGenerateRequest,
    LLMGenerateResponse,
)

router = APIRouter()


@router.post("/llm/generate", response_model=LLMGenerateResponse)
async def generate_llm(
    request: LLMGenerateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> LLMGenerateResponse:
    """通过 Gateway 调用 LLM。"""

    try:
        provider_config = await model_provider_db.get_by_key(
            session, request.org_id, request.provider
        )
        if provider_config is None or not provider_config.is_enabled:
            raise GatewayProviderError(f"未配置可用模型供应商：{request.provider}")

        api_key = (
            decrypt_api_key(provider_config.api_key_encrypted)
            if provider_config.api_key_encrypted
            else ""
        )
        provider_gateway = LLMGateway(
            providers={
                provider_config.provider_key: OpenAICompatibleProvider(
                    base_url=provider_config.base_url,
                    api_key=api_key,
                    provider_key=provider_config.provider_key,
                )
            },
            limiter=llm_gateway.limiter,
        )
        response = await provider_gateway.generate(
            LLMCallRequest(
                provider=request.provider,
                model=request.model,
                prompt=request.prompt,
                parameters=request.parameters,
                metadata={
                    "source": "gateway_api",
                    "org_id": request.org_id,
                    "actor_user_id": request.actor_user_id,
                },
            )
        )
        llm_gateway.call_logs.extend(provider_gateway.list_logs())
    except GatewayProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return LLMGenerateResponse(
        text=response.text,
        provider=response.provider,
        model=response.model,
        usage=response.usage,
    )


@router.get("/llm/logs", response_model=list[LLMCallLogResponse])
async def list_llm_logs() -> list[LLMCallLogResponse]:
    """查看 LLM 调用日志。"""

    return [_to_log_response(log) for log in llm_gateway.list_logs()]


def _to_log_response(log: LLMCallLog) -> LLMCallLogResponse:
    """把 LLM 调用日志转换为 API 响应。"""

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
