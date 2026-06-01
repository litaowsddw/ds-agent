"""后台 Agent API Schema。"""

from pydantic import BaseModel


class BackgroundAgentRegisterRequest(BaseModel):
    actor_user_id: str
    org_id: str
    agent_type: str
    interval_seconds: int = 300


class BackgroundAgentResponse(BaseModel):
    config_id: str
    org_id: str
    agent_type: str
    enabled: bool
    interval_seconds: int
    status: str
    last_error: str


class BackgroundAgentTriggerRequest(BaseModel):
    actor_user_id: str
