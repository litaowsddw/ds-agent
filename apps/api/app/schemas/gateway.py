"""Gateway API schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMGenerateRequest(BaseModel):
    """Client-controlled LLM generation parameters only."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="", description="LLM provider key")
    model: str = Field(default="", description="Model name")
    prompt: str = Field(min_length=1, description="Prompt")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Model parameters")


class LLMGenerateResponse(BaseModel):
    """Gateway generation response."""

    text: str
    provider: str
    model: str
    usage: dict[str, int]


class LLMCallLogResponse(BaseModel):
    """Gateway diagnostic log response."""

    call_id: str
    provider: str
    model: str
    prompt_preview: str
    prefix_hash: str
    status: str
    usage: dict[str, int]
    error_message: str
    metadata: dict[str, Any]
