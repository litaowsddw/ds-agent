"""用户、组织、群组和权限隔离 API。

MVP 阶段使用显式 `actor_user_id` 作为操作者身份。正式登录模块完成后，
这些字段会替换为认证中间件解析出的当前用户。
"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.identity import AuditLog, Membership, Organization, Team, User
from apps.api.app.schemas.identity import (
    AddMemberRequest,
    AuditLogResponse,
    MembershipResponse,
    OrganizationCreateRequest,
    OrganizationResponse,
    TeamCreateRequest,
    TeamResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from apps.api.app.services.identity_store import identity_store

router = APIRouter()


@router.post("/users/register", response_model=UserResponse)
async def register_user(request: UserRegisterRequest) -> UserResponse:
    """注册用户。"""

    try:
        user = identity_store.register_user(
            email=request.email,
            display_name=request.display_name,
            password=request.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_user_response(user)


@router.post("/users/login", response_model=UserResponse)
async def login_user(request: UserLoginRequest) -> UserResponse:
    """校验用户登录。"""

    try:
        user = identity_store.authenticate_user(email=request.email, password=request.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return _to_user_response(user)


@router.post("/organizations", response_model=OrganizationResponse)
async def create_organization(request: OrganizationCreateRequest) -> OrganizationResponse:
    """创建组织。"""

    try:
        organization = identity_store.create_organization(
            creator_user_id=request.creator_user_id,
            name=request.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_organization_response(organization)


@router.get("/users/{user_id}/organizations", response_model=list[OrganizationResponse])
async def list_user_organizations(user_id: str) -> list[OrganizationResponse]:
    """列出用户所属组织。"""

    try:
        organizations = identity_store.list_organizations_for_user(user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [_to_organization_response(organization) for organization in organizations]


@router.post("/organizations/{org_id}/teams", response_model=TeamResponse)
async def create_team(org_id: str, request: TeamCreateRequest) -> TeamResponse:
    """在组织内创建群组。"""

    try:
        team = identity_store.create_team(
            actor_user_id=request.actor_user_id,
            org_id=org_id,
            name=request.name,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_team_response(team)


@router.get("/organizations/{org_id}/teams", response_model=list[TeamResponse])
async def list_teams(
    org_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[TeamResponse]:
    """列出组织内群组。"""

    try:
        teams = identity_store.list_teams(actor_user_id=actor_user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_team_response(team) for team in teams]


@router.post("/organizations/{org_id}/members", response_model=MembershipResponse)
async def add_member(org_id: str, request: AddMemberRequest) -> MembershipResponse:
    """向组织添加成员。"""

    try:
        membership = identity_store.add_member(
            actor_user_id=request.actor_user_id,
            org_id=org_id,
            target_user_id=request.target_user_id,
            role=request.role,
            team_ids=request.team_ids,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _to_membership_response(membership)


@router.get("/organizations/{org_id}/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    org_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[AuditLogResponse]:
    """列出组织审计日志。"""

    try:
        audit_logs = identity_store.list_audit_logs(actor_user_id=actor_user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return [_to_audit_log_response(audit_log) for audit_log in audit_logs]


def _to_user_response(user: User) -> UserResponse:
    """把用户领域模型转换为 API 响应。"""

    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
    )


def _to_organization_response(organization: Organization) -> OrganizationResponse:
    """把组织领域模型转换为 API 响应。"""

    return OrganizationResponse(
        org_id=organization.org_id,
        name=organization.name,
        created_by=organization.created_by,
    )


def _to_team_response(team: Team) -> TeamResponse:
    """把群组领域模型转换为 API 响应。"""

    return TeamResponse(
        team_id=team.team_id,
        org_id=team.org_id,
        name=team.name,
        created_by=team.created_by,
    )


def _to_membership_response(membership: Membership) -> MembershipResponse:
    """把成员关系领域模型转换为 API 响应。"""

    return MembershipResponse(
        membership_id=membership.membership_id,
        org_id=membership.org_id,
        user_id=membership.user_id,
        role=membership.role,
        team_ids=membership.team_ids,
    )


def _to_audit_log_response(audit_log: AuditLog) -> AuditLogResponse:
    """把审计日志领域模型转换为 API 响应。"""

    return AuditLogResponse(
        audit_id=audit_log.audit_id,
        org_id=audit_log.org_id,
        actor_user_id=audit_log.actor_user_id,
        action=audit_log.action.value,
        target_type=audit_log.target_type,
        target_id=audit_log.target_id,
        detail=audit_log.detail,
    )
