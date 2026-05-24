"""Gateway API。"""

from fastapi import APIRouter, HTTPException

from apps.api.app.gateway.llm import GatewayProviderError, LLMCallLog, LLMCallRequest, llm_gateway
from apps.api.app.schemas.gateway import (
    LLMCallLogResponse,
    LLMGenerateRequest,
    LLMGenerateResponse,
)

router = APIRouter()


@router.post("/llm/generate", response_model=LLMGenerateResponse)
async def generate_llm(request: LLMGenerateRequest) -> LLMGenerateResponse:
    """通过 Gateway 调用 LLM。"""

    try:
        response = llm_gateway.generate(
            LLMCallRequest(
                provider=request.provider,
                model=request.model,
                prompt=request.prompt,
                parameters=request.parameters,
                metadata={"source": "gateway_api"},
            )
        )
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
