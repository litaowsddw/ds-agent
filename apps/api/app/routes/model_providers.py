"""模型供应商配置 API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.model_provider import ModelProviderConfig
from apps.api.app.schemas.model_provider import ModelProviderCreateRequest, ModelProviderResponse
from apps.api.app.services.model_provider_store import model_provider_store

router = APIRouter()


@router.post("", response_model=ModelProviderResponse)
async def create_model_provider(request: ModelProviderCreateRequest) -> ModelProviderResponse:
    """创建或更新组织级模型供应商配置。"""

    try:
        provider = model_provider_store.create_provider(
            actor_user_id=request.actor_user_id,
            org_id=request.org_id,
            provider_key=request.provider_key,
            display_name=request.display_name,
            base_url=request.base_url,
            api_key=request.api_key,
            models=request.models,
            default_model=request.default_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_provider_response(provider)


@router.get("", response_model=list[ModelProviderResponse])
async def list_model_providers(
    actor_user_id: str = Query(description="操作用户 ID"),
    org_id: str = Query(description="组织 ID"),
) -> list[ModelProviderResponse]:
    """列出组织可用模型供应商配置。"""

    try:
        providers = model_provider_store.list_providers(actor_user_id=actor_user_id, org_id=org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_to_provider_response(provider) for provider in providers]


def _to_provider_response(provider: ModelProviderConfig) -> ModelProviderResponse:
    """把领域模型转换为 API 响应，避免泄露 API Key 明文。"""

    return ModelProviderResponse(
        provider_id=provider.provider_id,
        org_id=provider.org_id,
        provider_key=provider.provider_key,
        display_name=provider.display_name,
        base_url=provider.base_url,
        api_key_masked=_mask_api_key(provider.api_key),
        models=provider.models,
        default_model=provider.default_model,
        is_enabled=provider.is_enabled,
    )


def _mask_api_key(api_key: str) -> str:
    """生成接口响应中的密钥掩码。"""

    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"
