"""Session API Schema。"""

from pydantic import BaseModel, Field
from typing import Any

from apps.api.app.domain.session import MessageRole, SessionQueueMode, SessionStatus


class SessionCreateRequest(BaseModel):
    """创建 Session 请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    agent_id: str = Field(description="目标 Agent ID")
    queue_mode: SessionQueueMode = Field(default=SessionQueueMode.QUEUE, description="消息队列模式")


class SessionResponse(BaseModel):
    """Session 响应。"""

    session_id: str
    org_id: str
    agent_id: str
    user_id: str
    queue_mode: SessionQueueMode
    status: SessionStatus
    compact_summary: str


class MessageAppendRequest(BaseModel):
    """追加消息请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    role: MessageRole = Field(description="消息角色")
    content: str = Field(min_length=1, description="消息正文")


class MessageResponse(BaseModel):
    """消息响应。"""

    message_id: str
    session_id: str
    org_id: str
    agent_id: str
    role: MessageRole
    content: str
    sequence: int
    estimated_tokens: int
    compacted: bool
    meta_info: dict[str, Any] = Field(default_factory=dict)


class SessionCompactRequest(BaseModel):
    """压缩 Session 请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    summary: str = Field(description="压缩摘要")
