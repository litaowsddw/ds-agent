"""模型供应商领域模型。"""

from dataclasses import dataclass, field
from datetime import datetime

from apps.api.app.domain.identity import utc_now


@dataclass(slots=True)
class ModelProviderConfig:
    """组织级模型供应商配置。"""

    # provider_id 是配置记录的唯一 ID。
    provider_id: str

    # org_id 是该供应商配置归属的组织 ID。
    org_id: str

    # provider_key 是工作流节点引用的供应商 key，例如 openai、deepseek。
    provider_key: str

    # display_name 是展示给用户看的供应商名称。
    display_name: str

    # base_url 是 OpenAI-compatible API 根地址。
    base_url: str

    # api_key 是供应商密钥，仅保存在后端，接口响应只返回掩码。
    api_key: str

    # models 是该供应商下可选模型列表。
    models: list[str] = field(default_factory=list)

    # default_model 是前端创建 LLM 节点时默认选中的模型。
    default_model: str = ""

    # is_enabled 表示该供应商是否可用于 Gateway 调用。
    is_enabled: bool = True

    # created_by 是创建该配置的用户 ID。
    created_by: str = ""

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)

    # updated_at 是更新时间。
    updated_at: datetime = field(default_factory=utc_now)
