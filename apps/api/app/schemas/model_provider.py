"""模型供应商 API Schema。"""

from pydantic import BaseModel, Field


class ModelProviderCreateRequest(BaseModel):
    """创建模型供应商配置请求。"""

    actor_user_id: str = Field(description="操作用户 ID")
    org_id: str = Field(description="组织 ID")
    provider_key: str = Field(min_length=1, max_length=40, description="供应商 key")
    display_name: str = Field(min_length=1, max_length=80, description="展示名称")
    base_url: str = Field(min_length=1, description="OpenAI-compatible API 根地址")
    api_key: str = Field(default="", description="供应商 API Key")
    models: list[str] = Field(default_factory=list, description="可选模型列表")
    default_model: str = Field(default="", description="默认模型")


class ModelProviderResponse(BaseModel):
    """模型供应商配置响应。"""

    provider_id: str
    org_id: str
    provider_key: str
    display_name: str
    base_url: str
    api_key_masked: str
    models: list[str]
    default_model: str
    is_enabled: bool
