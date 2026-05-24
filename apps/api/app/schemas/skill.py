"""Skill API Schema。"""

from pydantic import BaseModel, Field

from apps.api.app.domain.skill import SkillScope


class SkillRegisterRequest(BaseModel):
    """注册 Skill 请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    org_id: str = Field(description="组织 ID")
    scope: SkillScope = Field(description="Skill 来源层级")
    content: str = Field(description="完整 SKILL.md 内容")
    team_id: str | None = Field(default=None, description="Team 级 Skill 所属群组")
    agent_id: str | None = Field(default=None, description="Agent 级 Skill 所属 Agent")


class SkillResponse(BaseModel):
    """Skill 响应。"""

    skill_id: str
    org_id: str
    team_id: str | None
    agent_id: str | None
    scope: SkillScope
    name: str
    description: str
    enabled: bool


class AgentSkillPolicyRequest(BaseModel):
    """Agent Skill 授权请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    skill_id: str = Field(description="Skill ID")
    allowed: bool = Field(description="是否允许使用")


class SkillSummaryResponse(BaseModel):
    """Skill 摘要响应。"""

    skill_id: str
    name: str
    description: str
    scope: str

