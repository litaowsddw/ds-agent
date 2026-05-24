"""Skill 领域模型。

Skill 参考 OpenClaw 的 `SKILL.md` 组织方式，用于把专门能力按摘要注入上下文，
并在真正触发时加载完整说明。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from apps.api.app.domain.identity import utc_now


class SkillScope(StrEnum):
    """Skill 来源层级。"""

    BUNDLED = "bundled"
    ORGANIZATION = "organization"
    TEAM = "team"
    AGENT = "agent"


@dataclass(slots=True)
class Skill:
    """Skill 实体。"""

    # skill_id 是 Skill 唯一标识。
    skill_id: str

    # org_id 是 Skill 所属组织；bundled skill 可以为空字符串。
    org_id: str

    # team_id 是 Team 级 Skill 所属群组。
    team_id: str | None

    # agent_id 是 Agent 级 Skill 所属 Agent。
    agent_id: str | None

    # scope 表示 Skill 来源层级。
    scope: SkillScope

    # name 是 Skill 稳定名称。
    name: str

    # description 是 Skill 摘要，默认注入上下文时只使用它。
    description: str

    # content 是完整 SKILL.md 内容，只有触发时才加载。
    content: str

    # enabled 表示 Skill 是否启用。
    enabled: bool = True

    # created_by 是创建者用户 ID。
    created_by: str = ""

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class AgentSkillPolicy:
    """Agent Skill 授权策略。"""

    # agent_id 是被授权的 Agent。
    agent_id: str

    # skill_id 是被授权的 Skill。
    skill_id: str

    # allowed 表示是否允许 Agent 使用该 Skill。
    allowed: bool

