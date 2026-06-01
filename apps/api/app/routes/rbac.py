"""RBAC 权限管理 API。

提供动态权限策略的 CRUD 和权限检查接口。
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity import new_id
from app.core.auth import AuthenticatedUser
from app.services.db.identity_db import membership_db, rbac_policy_db
from app.services.rbac import Permission, RBACService, RBACPolicy, ROLE_PERMISSIONS, rbac_service

router = APIRouter()


class PolicyCreateRequest(BaseModel):
    """创建动态策略请求。"""

    role: str = Field(description="角色名称")
    permission: str = Field(description="权限标识")
    allowed: bool = Field(default=True, description="是否允许")
    priority: int = Field(default=0, description="优先级，数值越大优先级越高")


class PolicyResponse(BaseModel):
    """策略响应。"""

    policy_id: str
    org_id: str
    role: str
    permission: str
    allowed: bool
    priority: int
    created_by: str


class PermissionCheckRequest(BaseModel):
    """权限检查请求。"""

    permission: str = Field(description="要检查的权限标识")


class PermissionCheckResponse(BaseModel):
    """权限检查响应。"""

    allowed: bool
    permission: str
    role: str


class RolePermissionsResponse(BaseModel):
    """角色权限列表响应。"""

    role: str
    permissions: list[str]


@router.post("/organizations/{org_id}/policies", response_model=PolicyResponse)
async def create_policy(
    org_id: str,
    request: PolicyCreateRequest,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> PolicyResponse:
    """创建组织级动态权限策略（需要 admin 角色）。"""
    # 验证权限
    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=org_id, required_role="admin"
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 验证 permission 是否合法
    try:
        Permission(request.permission)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的权限标识：{request.permission}",
        )

    try:
        policy = await rbac_policy_db.create_policy(
            session,
            policy_id=new_id("pol"),
            org_id=org_id,
            role=request.role,
            permission=request.permission,
            allowed=request.allowed,
            priority=request.priority,
            created_by=auth.user_id,
        )
        await session.commit()

        # 同步到内存 RBAC 服务
        rbac_service.add_policy(RBACPolicy(
            policy_id=policy.policy_id,
            org_id=policy.org_id,
            role=policy.role,
            permission=policy.permission,
            allowed=policy.allowed,
            created_by=policy.created_by,
            priority=policy.priority,
        ))
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_policy_response(policy)


@router.get("/organizations/{org_id}/policies", response_model=list[PolicyResponse])
async def list_policies(
    org_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[PolicyResponse]:
    """列出组织所有动态策略。"""
    try:
        await membership_db.assert_org_access(session, user_id=auth.user_id, org_id=org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    policies = await rbac_policy_db.list_org_policies(session, org_id)
    return [_to_policy_response(p) for p in policies]


@router.delete("/organizations/{org_id}/policies/{policy_id}")
async def delete_policy(
    org_id: str,
    policy_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """删除动态策略。"""
    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=org_id, required_role="admin"
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    deleted = await rbac_policy_db.delete_by_id(session, policy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="策略不存在")

    await session.commit()

    # 从内存 RBAC 服务中移除
    rbac_service.remove_policy(org_id, policy_id)

    return {"deleted": True}


@router.post("/organizations/{org_id}/check", response_model=PermissionCheckResponse)
async def check_permission(
    org_id: str,
    request: PermissionCheckRequest,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> PermissionCheckResponse:
    """检查当前用户在指定组织中是否拥有某权限。"""
    membership = await membership_db.get_membership(session, org_id, auth.user_id)
    if membership is None:
        return PermissionCheckResponse(allowed=False, permission=request.permission, role="anonymous")

    try:
        permission = Permission(request.permission)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的权限标识：{request.permission}")

    allowed = rbac_service.has_permission(membership, permission)
    return PermissionCheckResponse(
        allowed=allowed,
        permission=request.permission,
        role=membership.role,
    )


@router.get("/roles", response_model=list[RolePermissionsResponse])
async def list_role_permissions() -> list[RolePermissionsResponse]:
    """列出所有角色的默认权限。"""
    result = []
    for role, perms in ROLE_PERMISSIONS.items():
        result.append(RolePermissionsResponse(
            role=role.value,
            permissions=[p.value for p in sorted(perms, key=lambda x: x.value)],
        ))
    return result


def _to_policy_response(policy) -> PolicyResponse:
    return PolicyResponse(
        policy_id=policy.policy_id,
        org_id=policy.org_id,
        role=policy.role,
        permission=policy.permission,
        allowed=policy.allowed,
        priority=policy.priority,
        created_by=policy.created_by,
    )
