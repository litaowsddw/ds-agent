"""Agent 内存管理器。

MemoryManager 负责 Session Memory、Working Memory、Long-term Memory 和 Artifact Memory。
MVP 阶段先定义写入和召回接口，后续接入 PostgreSQL、pgvector 和 Redis。
"""

from dataclasses import dataclass


@dataclass(slots=True)
class MemoryItem:
    """一条 Agent 记忆。"""

    # memory_id 是记忆唯一标识。
    memory_id: str

    # memory_type 表示记忆类型，例如 preference、fact、task、artifact。
    memory_type: str

    # content 是记忆正文，写入长期记忆前必须经过敏感信息策略检查。
    content: str


class MemoryManager:
    """管理 Agent 的记忆写入和召回。"""

    def recall(self, org_id: str, agent_id: str, query: str) -> list[MemoryItem]:
        """根据当前输入召回相关记忆。"""

        # org_id 是第一层隔离边界。
        _org_id = org_id

        # agent_id 是第二层隔离边界。
        _agent_id = agent_id

        # query 是用于检索记忆的当前问题或任务目标。
        _query = query

        return []

