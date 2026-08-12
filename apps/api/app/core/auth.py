"""JWT 认证依赖注入。

提供 FastAPI Depends 用的认证中间件，替代 actor_user_id 显式传参。
支持：
- Bearer Token（JWT）
- API Key（服务间调用）
- 降级模式（开发环境允许 actor_user_id 查询参数）
"""

import os
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import verify_access_token, JWTPayload

# 是否启用严格 JWT 模式（生产环境应设为 true）
_STRICT_JWT = os.getenv("STRICT_JWT", "false").lower() == "true"

# Bearer Token 提取器
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthContext:
    """认证上下文，注入到路由处理函数中。"""

    user_id: str
    email: str
    org_id: str | None
    role: str | None
    is_authenticated: bool = True

    @classmethod
    def from_jwt(cls, payload: JWTPayload) -> "AuthContext":
        """从 JWT 载荷构建认证上下文。"""
        return cls(
            user_id=payload.user_id,
            email=payload.email,
            org_id=payload.org_id,
            role=payload.role,
            is_authenticated=True,
        )

    @classmethod
    def anonymous(cls) -> "AuthContext":
        """匿名上下文（开发环境降级）。"""
        return cls(
            user_id="",
            email="",
            org_id=None,
            role=None,
            is_authenticated=False,
        )


async def get_auth_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
    actor_user_id: Annotated[str | None, Query(description="开发环境：操作者用户 ID")] = None,
) -> AuthContext:
    """获取当前请求的认证上下文。

    认证优先级：
    1. Authorization: Bearer <JWT> — 最高优先级
    2. X-API-Key <api_key> — 服务间调用
    3. actor_user_id 查询参数 — 开发环境降级
    """
    # 1. Bearer JWT
    if credentials is not None:
        payload = verify_access_token(credentials.credentials)
        if payload is not None:
            return AuthContext.from_jwt(payload)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的 JWT Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. X-API-Key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # API Key 认证：查找对应的 service account
        # MVP 阶段：直接把 API Key 映射到 user_id
        ctx = _resolve_api_key(api_key)
        if ctx is not None:
            return ctx

    # 3. 开发环境降级：actor_user_id 查询参数
    if actor_user_id and not _STRICT_JWT:
        return AuthContext(
            user_id=actor_user_id,
            email="",
            org_id=None,
            role=None,
            is_authenticated=True,
        )

    # 严格模式：必须认证
    if _STRICT_JWT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证信息，请提供 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 非严格模式：允许匿名（路由级别自行判断）
    return AuthContext.anonymous()


def require_auth(auth: AuthContext) -> AuthContext:
    """要求必须认证，否则 401。"""
    if not auth.is_authenticated or not auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="此操作需要登录",
        )
    return auth


def resolve_actor(auth: AuthContext, legacy_actor: str | None = None) -> str:
    """计算请求的有效操作者。

    优先级（与安全边界一致）：
    1. JWT 身份（生产 STRICT_JWT 模式下永远走这里）
    2. 开发降级期历史契约里的 body/query actor_user_id
    两者皆空时拒绝为 401。生产环境因 get_auth_context 强制 JWT，
    legacy 参数永远不会被采纳；开发/测试环境保留旧契约可用性。
    """
    actor = auth.user_id or (legacy_actor or "").strip()
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证信息，请提供 Bearer Token",
        )
    return actor


def require_org(auth: AuthContext, org_id: str) -> AuthContext:
    """要求用户属于指定组织，否则 403。"""
    require_auth(auth)
    if auth.org_id and auth.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"用户不属于组织 {org_id}",
        )
    return auth


# 便捷类型别名
CurrentUser = Annotated[AuthContext, Depends(get_auth_context)]
AuthenticatedUser = Annotated[AuthContext, Depends(lambda auth=Depends(get_auth_context): require_auth(auth))]


# ── API Key 解析（MVP 实现） ──

# 服务间 API Key 映射（生产环境应存数据库）
_SERVICE_ACCOUNTS: dict[str, AuthContext] = {}


def register_service_account(api_key: str, user_id: str, org_id: str | None = None) -> None:
    """注册服务间调用的 API Key。"""
    _SERVICE_ACCOUNTS[api_key] = AuthContext(
        user_id=user_id,
        email=f"service:{user_id}",
        org_id=org_id,
        role="admin",
        is_authenticated=True,
    )


def _resolve_api_key(api_key: str) -> AuthContext | None:
    """解析 API Key 到认证上下文。"""
    return _SERVICE_ACCOUNTS.get(api_key)
