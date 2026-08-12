"""用户、组织、群组和权限隔离 API（数据库版本）。

使用 SQLAlchemy 异步数据库服务替代内存 store。
Sprint 4: 登录接口返回 JWT Token，部分接口支持 JWT 认证。
"""

import json
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.identity import UserModel, OrganizationModel, TeamModel, MembershipModel, AuditLogModel
from app.schemas.identity import (
    AddMemberRequest,
    AuditLogResponse,
    LoginResponse,
    MembershipResponse,
    OrganizationCreateRequest,
    OrganizationResponse,
    TeamCreateRequest,
    TeamResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.db.identity_db import (
    user_db,
    org_db,
    team_db,
    membership_db,
    audit_log_db,
)
from app.domain.identity import AuditAction, new_id
from app.core.security import hash_password, verify_password, create_access_token
from app.core.auth import CurrentUser, AuthenticatedUser, AuthContext, require_auth, resolve_actor

router = APIRouter()


@router.post("/users/register", response_model=UserResponse)
async def register_user(
    request: UserRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """注册用户。"""
    try:
        existing = await user_db.get_by_email(session, request.email)
        if existing is not None:
            raise ValueError("邮箱已注册")

        user = await user_db.create_user(
            session,
            user_id=new_id("usr"),
            email=request.email,
            display_name=request.display_name,
            password_hash=hash_password(request.password),
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_user_response(user)


@router.post("/users/login", response_model=LoginResponse)
async def login_user(
    request: UserLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    """校验用户登录，返回 JWT Token。"""
    user = await user_db.get_by_email(session, request.email)
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    # 查找用户的第一个组织作为默认上下文
    memberships = await membership_db.list_user_memberships(session, user.user_id)
    default_org_id = memberships[0].org_id if memberships else None
    default_role = memberships[0].role if memberships else None

    # 签发 JWT
    token = create_access_token(
        user_id=user.user_id,
        email=user.email,
        org_id=default_org_id,
        role=default_role,
    )

    return LoginResponse(
        user=_to_user_response(user),
        token=TokenResponse(
            access_token=token,
            token_type="bearer",
        ),
        default_org_id=default_org_id,
        default_role=default_role,
    )


@router.post("/users/switch-org", response_model=TokenResponse)
async def switch_organization(
    org_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """切换当前用户的工作组织，重新签发 JWT。"""
    # 验证用户属于该组织
    membership = await membership_db.get_membership(session, org_id, auth.user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="用户不属于该组织")

    # 重新签发 JWT（带新 org_id 和 role）
    token = create_access_token(
        user_id=auth.user_id,
        email=auth.email,
        org_id=org_id,
        role=membership.role,
    )

    return TokenResponse(access_token=token, token_type="bearer")


@router.get("/users/me", response_model=UserResponse)
async def get_current_user(
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """获取当前登录用户信息。"""
    user = await user_db.get_by_id(session, auth.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _to_user_response(user)


@router.post("/organizations", response_model=OrganizationResponse)
async def create_organization(
    request: OrganizationCreateRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    """创建组织。"""
    # 优先使用 JWT 中的 user_id，降级使用请求体中的 creator_user_id
    creator_id = auth.user_id or request.creator_user_id
    if not creator_id:
        raise HTTPException(status_code=401, detail="需要登录才能创建组织")

    try:
        org = await org_db.create_org(
            session,
            org_id=new_id("org"),
            name=request.name,
            created_by=creator_id,
        )

        # 创建者自动成为 owner
        await membership_db.add_member(
            session,
            membership_id=new_id("mem"),
            org_id=org.org_id,
            user_id=creator_id,
            role="owner",
        )
        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=org.org_id,
            actor_user_id=creator_id,
            action=AuditAction.ORGANIZATION_CREATED,
            resource_type="organization",
            resource_id=org.org_id,
            detail={"name": org.name},
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_organization_response(org)


@router.get("/users/{user_id}/organizations", response_model=list[OrganizationResponse])
async def list_user_organizations(
    user_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[OrganizationResponse]:
    """列出用户所属组织（仅允许查询本人）。"""
    if user_id != auth.user_id:
        raise HTTPException(status_code=403, detail="只能查询本人的组织列表")
    orgs = await org_db.list_user_orgs(session, user_id)
    return [_to_organization_response(org) for org in orgs]


@router.post("/organizations/{org_id}/teams", response_model=TeamResponse)
async def create_team(
    org_id: str,
    request: TeamCreateRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> TeamResponse:
    """在组织内创建群组。"""
    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=org_id, required_role="admin"
        )
        team = await team_db.create_team(
            session,
            team_id=new_id("team"),
            org_id=org_id,
            name=request.name,
            created_by=actor_user_id,
        )
        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=AuditAction.TEAM_CREATED,
            resource_type="team",
            resource_id=team.team_id,
            detail={"name": team.name},
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return _to_team_response(team)


@router.get("/organizations/{org_id}/teams", response_model=list[TeamResponse])
async def list_teams(
    org_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[TeamResponse]:
    """列出组织内群组。"""
    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=org_id
        )
        teams = await team_db.list_org_teams(session, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_team_response(team) for team in teams]


@router.post("/organizations/{org_id}/members", response_model=MembershipResponse)
async def add_member(
    org_id: str,
    request: AddMemberRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> MembershipResponse:
    """向组织添加成员。"""
    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=org_id, required_role="admin"
        )
        membership = await membership_db.add_member(
            session,
            membership_id=new_id("mem"),
            org_id=org_id,
            user_id=request.target_user_id,
            role=request.role,
            team_ids=request.team_ids,
        )
        await audit_log_db.append_log(
            session,
            log_id=new_id("aud"),
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=AuditAction.MEMBER_JOINED,
            resource_type="membership",
            resource_id=membership.membership_id,
            detail={
                "user_id": membership.user_id,
                "role": membership.role,
                "team_ids": json.loads(membership.team_ids_json),
            },
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return _to_membership_response(membership)


@router.get("/organizations/{org_id}/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    org_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[AuditLogResponse]:
    """列出组织审计日志。"""
    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=org_id
        )
        logs, _ = await audit_log_db.list_org_logs(session, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_audit_log_response(log) for log in logs]


def _to_user_response(user: UserModel) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
    )


def _to_organization_response(org: OrganizationModel) -> OrganizationResponse:
    return OrganizationResponse(
        org_id=org.org_id,
        name=org.name,
        created_by=org.created_by,
    )


def _to_team_response(team: TeamModel) -> TeamResponse:
    return TeamResponse(
        team_id=team.team_id,
        org_id=team.org_id,
        name=team.name,
        created_by=team.created_by,
    )


def _to_membership_response(membership: MembershipModel) -> MembershipResponse:
    return MembershipResponse(
        membership_id=membership.membership_id,
        org_id=membership.org_id,
        user_id=membership.user_id,
        role=membership.role,
        team_ids=json.loads(membership.team_ids_json),
    )


def _to_audit_log_response(log: AuditLogModel) -> AuditLogResponse:
    return AuditLogResponse(
        audit_id=log.log_id,
        org_id=log.org_id,
        actor_user_id=log.actor_user_id,
        action=log.action,
        target_type=log.resource_type,
        target_id=log.resource_id,
        detail=_parse_audit_detail(log.detail),
    )


def _parse_audit_detail(raw_detail: str | None) -> dict[str, object]:
    """Return only JSON objects from audit storage, tolerating legacy values."""
    if not raw_detail:
        return {}

    try:
        parsed = json.loads(raw_detail)
    except (TypeError, json.JSONDecodeError):
        return {}

    return parsed if isinstance(parsed, dict) else {}
