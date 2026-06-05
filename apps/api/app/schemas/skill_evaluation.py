"""Skill evaluation API schemas."""

from pydantic import BaseModel, Field


class SkillEvaluationResponse(BaseModel):
    evaluation_id: str
    org_id: str
    agent_id: str
    skill_id: str
    session_id: str | None = None
    user_input: str
    assistant_output: str
    status: str
    score: float | None = None
    failure_reason: str
    improvement_suggestion: str
    proposed_skill_patch: str
    applied: bool
    created_by: str
    created_at: str


class SkillEvaluationUpdateRequest(BaseModel):
    actor_user_id: str = Field(description="操作者用户 ID")
    score: float = Field(ge=0, le=1, description="0-1 评分")
    failure_reason: str = Field(default="", max_length=4000, description="失败原因")
    improvement_suggestion: str = Field(default="", max_length=8000, description="改进建议")


class SkillEvaluationSuggestRequest(BaseModel):
    actor_user_id: str = Field(description="操作者用户 ID")


class SkillEvaluationDecisionRequest(BaseModel):
    actor_user_id: str = Field(description="操作者用户 ID")
    decision: str = Field(pattern="^(applied|rejected)$", description="人工决策")
