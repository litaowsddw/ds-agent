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
    # Provider usage may include nested vendor-specific detail objects, e.g.
    # OpenAI-compatible prompt_tokens_details.cached_tokens.
    usage: dict[str, Any]


class LLMCallLogResponse(BaseModel):
    """Gateway diagnostic log response."""

    call_id: str
    provider: str
    model: str
    prefix_hash: str
    status: str
    usage: dict[str, Any]
    error_message: str
    metadata: dict[str, Any]
