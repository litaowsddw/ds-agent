"""Gateway API Schema。"""

from typing import Any

from pydantic import BaseModel, Field


class LLMGenerateRequest(BaseModel):
    """LLM 生成请求。"""

    provider: str = Field(default="mock", description="LLM Provider 名称")
    model: str = Field(default="mock-model", description="模型名称")
    prompt: str = Field(min_length=1, description="提示词")
    parameters: dict[str, Any] = Field(default_factory=dict, description="模型参数")


class LLMGenerateResponse(BaseModel):
    """LLM 生成响应。"""

    text: str
    provider: str
    model: str
    usage: dict[str, int]


class LLMCallLogResponse(BaseModel):
    """LLM 调用日志响应。"""

    call_id: str
    provider: str
    model: str
    prompt_preview: str
    prefix_hash: str
    status: str
    usage: dict[str, int]
    error_message: str
    metadata: dict[str, Any]
