"""Memory 领域模型。

Memory 用于保存 Agent 的长期事实、偏好、任务经验和 artifact 摘要。
MVP 阶段先提供按 org/agent 隔离的关键词召回，后续替换为向量检索和重排。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from apps.api.app.domain.identity import utc_now


class MemoryType(StrEnum):
    """记忆类型。"""

    FACT = "fact"
    PREFERENCE = "preference"
    TASK = "task"
    DECISION = "decision"
    ARTIFACT = "artifact"


@dataclass(slots=True)
class Memory:
    """Agent 长期记忆。"""

    # memory_id 是记忆唯一标识。
    memory_id: str

    # org_id 是记忆所属组织。
    org_id: str

    # agent_id 是记忆所属 Agent。
    agent_id: str

    # user_id 是记忆来源用户。
    user_id: str

    # memory_type 是记忆类型。
    memory_type: MemoryType

    # content 是记忆正文。
    content: str

    # summary 是记忆摘要，用于上下文注入。
    summary: str

    # confidence 是记忆置信度，范围 0 到 1。
    confidence: float = 1.0

    # source 是记忆来源，例如 manual、compaction、tool。
    source: str = "manual"

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)
