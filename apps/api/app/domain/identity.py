"""用户、组织、群组和权限领域模型。

模块 2 的核心是建立多租户隔离边界。所有 Agent、Workflow、Skill、MCP、
Memory 等后续资源，都必须挂在这里定义的组织和群组边界之下。
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


def utc_now() -> datetime:
    """返回带时区的 UTC 时间。"""

    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """生成带业务前缀的 ID。

    参数：
        prefix: 业务前缀，例如 usr、org、team。
    """

    # random_part 是 UUID 的十六进制字符串，用于保证本地 MVP 数据唯一。
    random_part = uuid4().hex
    return f"{prefix}_{random_part}"


class OrganizationRole(StrEnum):
    """组织成员角色。"""

    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class AuditAction(StrEnum):
    """审计动作类型。"""

    USER_REGISTERED = "user.registered"
    ORGANIZATION_CREATED = "organization.created"
    TEAM_CREATED = "team.created"
    MEMBER_JOINED = "member.joined"
    PERMISSION_CHECKED = "permission.checked"


@dataclass(slots=True)
class User:
    """用户实体。"""

    # user_id 是用户唯一标识，后续会作为 created_by、updated_by 等审计字段来源。
    user_id: str

    # email 是用户登录账号，MVP 阶段要求全局唯一。
    email: str

    # display_name 是前端展示名称。
    display_name: str

    # password_hash 是密码哈希，禁止保存明文密码。
    password_hash: str

    # created_at 是用户创建时间，用于审计和排序。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Organization:
    """组织实体，也是多租户隔离的第一层边界。"""

    # org_id 是组织唯一标识，所有核心资源必须带 org_id。
    org_id: str

    # name 是组织名称。
    name: str

    # created_by 是创建该组织的用户 ID。
    created_by: str

    # created_at 是组织创建时间。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Team:
    """群组实体，位于组织之下，用于更细粒度资源授权。"""

    # team_id 是群组唯一标识。
    team_id: str

    # org_id 是群组所属组织。
    org_id: str

    # name 是群组名称。
    name: str

    # created_by 是创建群组的用户 ID。
    created_by: str

    # created_at 是群组创建时间。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Membership:
    """组织成员关系。"""

    # membership_id 是成员关系唯一标识。
    membership_id: str

    # org_id 是成员所属组织。
    org_id: str

    # user_id 是成员用户 ID。
    user_id: str

    # role 是用户在组织内的角色。
    role: OrganizationRole

    # team_ids 表示用户加入的群组 ID 列表。
    team_ids: list[str] = field(default_factory=list)

    # created_at 是成员加入时间。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class AuditLog:
    """审计日志实体。"""

    # audit_id 是审计记录唯一标识。
    audit_id: str

    # org_id 是审计记录所属组织；平台级事件可以为空字符串。
    org_id: str

    # actor_user_id 是触发动作的用户 ID。
    actor_user_id: str

    # action 是审计动作类型。
    action: AuditAction

    # target_type 是被操作对象类型，例如 user、organization、team。
    target_type: str

    # target_id 是被操作对象 ID。
    target_id: str

    # detail 保存结构化附加信息，注意不能写入密钥、密码等敏感数据。
    detail: dict[str, object] = field(default_factory=dict)

    # created_at 是审计发生时间。
    created_at: datetime = field(default_factory=utc_now)
