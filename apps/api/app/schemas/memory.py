"""Memory API Schema。"""

from pydantic import BaseModel, Field

from apps.api.app.domain.memory import MemoryType


class MemoryCreateRequest(BaseModel):
    """创建记忆请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    agent_id: str = Field(description="Agent ID")
    memory_type: MemoryType = Field(description="记忆类型")
    content: str = Field(min_length=1, description="记忆正文")
    summary: str = Field(default="", description="记忆摘要")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    source: str = Field(default="manual", description="记忆来源")


class MemoryRecallRequest(BaseModel):
    """召回记忆请求。"""

    actor_user_id: str = Field(description="操作者用户 ID")
    agent_id: str = Field(description="Agent ID")
    query: str = Field(default="", description="召回查询")
    limit: int = Field(default=5, ge=1, le=20, description="返回数量")


class MemoryResponse(BaseModel):
    """记忆响应。"""

    memory_id: str
    org_id: str
    agent_id: str
    user_id: str
    memory_type: MemoryType
    content: str
    summary: str
    confidence: float
    source: str

