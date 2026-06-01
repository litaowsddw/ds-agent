"""身份与租户 API Schema。"""

from pydantic import BaseModel, EmailStr, Field

from apps.api.app.domain.identity import OrganizationRole


class UserRegisterRequest(BaseModel):
    """用户注册请求。"""

    email: EmailStr = Field(description="用户邮箱")
    display_name: str = Field(min_length=1, max_length=64, description="用户展示名称")
    password: str = Field(min_length=8, max_length=128, description="用户密码")


class UserLoginRequest(BaseModel):
    """用户登录请求。"""

    email: EmailStr = Field(description="用户邮箱")
    password: str = Field(min_length=8, max_length=128, description="用户密码")


class TokenResponse(BaseModel):
    """JWT Token 响应。"""

    access_token: str = Field(description="JWT Access Token")
    token_type: str = Field(default="bearer", description="Token 类型")


class LoginResponse(BaseModel):
    """登录响应（包含用户信息和 Token）。"""

    user: "UserResponse" = Field(description="用户信息")
    token: TokenResponse = Field(description="JWT Token")
    default_org_id: str | None = Field(default=None, description="默认组织 ID")
    default_role: str | None = Field(default=None, description="默认组织角色")


class UserResponse(BaseModel):
    """用户响应。"""

    user_id: str
    email: str
    display_name: str


class OrganizationCreateRequest(BaseModel):
    """创建组织请求。"""

    creator_user_id: str = Field(description="创建者用户 ID")
    name: str = Field(min_length=1, max_length=80, description="组织名称")


class OrganizationResponse(BaseModel):
    """组织响应。"""

    org_id: str
    name: str
    created_by: str


class TeamCreateRequest(BaseModel):
    """创建群组请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    name: str = Field(min_length=1, max_length=80, description="群组名称")


class TeamResponse(BaseModel):
    """群组响应。"""

    team_id: str
    org_id: str
    name: str
    created_by: str


class AddMemberRequest(BaseModel):
    """添加组织成员请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    target_user_id: str = Field(description="目标用户 ID")
    role: OrganizationRole = Field(description="目标用户角色")
    team_ids: list[str] = Field(default_factory=list, description="目标用户加入的群组")


class MembershipResponse(BaseModel):
    """成员关系响应。"""

    membership_id: str
    org_id: str
    user_id: str
    role: OrganizationRole
    team_ids: list[str]


class AuditLogResponse(BaseModel):
    """审计日志响应。"""

    audit_id: str
    org_id: str
    actor_user_id: str
    action: str
    target_type: str
    target_id: str
    detail: dict[str, object]
