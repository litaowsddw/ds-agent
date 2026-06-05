"""模型供应商配置 API。

Sprint 4: 集成 AES-256 加密存储 API Key，响应自动脱敏。
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity import new_id
from app.core.security import encrypt_api_key, decrypt_api_key, mask_api_key
from app.core.auth import CurrentUser, require_auth
from app.models.runtime import ModelProviderModel
from app.schemas.model_provider import ModelProviderCreateRequest, ModelProviderResponse
from app.services.db.runtime_db import model_provider_db

import json

router = APIRouter()


@router.post("", response_model=ModelProviderResponse)
async def create_model_provider(
    request: ModelProviderCreateRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> ModelProviderResponse:
    """创建或更新组织级模型供应商配置。

    API Key 在存储前自动加密，响应中仅返回脱敏版本。
    """
    # 优先使用 JWT 中的 user_id
    actor_user_id = auth.user_id or request.actor_user_id
    if not actor_user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    # 检查是否已存在同 org + provider_key 的配置
    existing = await model_provider_db.get_by_key(session, request.org_id, request.provider_key)

    # 加密 API Key
    encrypted_key = encrypt_api_key(request.api_key) if request.api_key else ""
    masked_key = mask_api_key(request.api_key) if request.api_key else ""

    if existing is not None:
        # 更新已有配置
        existing.display_name = request.display_name or existing.display_name
        existing.base_url = request.base_url.rstrip("/") or existing.base_url
        existing.api_key_encrypted = encrypted_key
        existing.api_key_masked = masked_key
        existing.models_json = json.dumps(request.models, ensure_ascii=False)
        existing.default_model = request.default_model or request.models[0] if request.models else existing.default_model
        existing.is_enabled = True
        await session.flush()
        await session.commit()
        return _to_provider_response(existing)

    try:
        provider = await model_provider_db.create_provider(
            session,
            provider_id=new_id("mdl"),
            org_id=request.org_id,
            provider_key=request.provider_key.strip().lower(),
            display_name=request.display_name,
            base_url=request.base_url.rstrip("/"),
            api_key_encrypted=encrypted_key,
            api_key_masked=masked_key,
            models=request.models,
            default_model=request.default_model or (request.models[0] if request.models else ""),
            is_enabled=True,
            created_by=actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_provider_response(provider)


@router.get("", response_model=list[ModelProviderResponse])
async def list_model_providers(
    auth: CurrentUser,
    org_id: str = Query(description="组织 ID"),
    actor_user_id: str = Query(default="", description="操作用户 ID（降级）"),
    session: AsyncSession = Depends(get_db_session),
) -> list[ModelProviderResponse]:
    """列出组织可用模型供应商配置。API Key 自动脱敏。"""
    providers = await model_provider_db.list_org_providers(session, org_id)
    return [_to_provider_response(p) for p in providers]


@router.get("/{provider_id}/decrypted-key")
async def get_decrypted_api_key(
    provider_id: str,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取解密后的 API Key（仅限服务间调用，需认证）。

    此端点供 Gateway 等内部服务调用，前端不应使用。
    """
    if not auth.is_authenticated:
        raise HTTPException(status_code=401, detail="需要认证")

    provider = await model_provider_db.get_by_id(session, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="供应商配置不存在")

    # 解密 API Key
    try:
        decrypted = decrypt_api_key(provider.api_key_encrypted) if provider.api_key_encrypted else ""
    except Exception:
        raise HTTPException(status_code=500, detail="API Key 解密失败")

    return {"provider_id": provider_id, "api_key": decrypted}


def _to_provider_response(provider: ModelProviderModel) -> ModelProviderResponse:
    """把 ORM 模型转换为 API 响应，API Key 使用脱敏版本。"""
    return ModelProviderResponse(
        provider_id=provider.provider_id,
        org_id=provider.org_id,
        provider_key=provider.provider_key,
        display_name=provider.display_name,
        base_url=provider.base_url,
        api_key_masked=provider.api_key_masked or "****",
        models=json.loads(provider.models_json) if provider.models_json else [],
        default_model=provider.default_model,
        is_enabled=provider.is_enabled,
    )
