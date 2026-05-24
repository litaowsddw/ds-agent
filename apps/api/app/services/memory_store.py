"""Memory Store。

MVP 使用内存存储和关键词召回。接口刻意保持接近未来向量检索形态：
写入时带类型、摘要和来源；召回时按 query、org、agent 做过滤。
"""

from apps.api.app.domain.identity import new_id
from apps.api.app.domain.memory import Memory, MemoryType
from apps.api.app.services.agent_store import AgentStore, agent_store
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission


class MemoryStore:
    """管理 Agent 长期记忆。"""

    def __init__(self, identity: IdentityStore, agents: AgentStore) -> None:
        # identity 用于组织权限校验。
        self.identity = identity

        # agents 用于读取 Agent 所属组织。
        self.agents = agents

        # memories_by_id 保存所有记忆。
        self.memories_by_id: dict[str, Memory] = {}

    def create_memory(
        self,
        actor_user_id: str,
        agent_id: str,
        memory_type: MemoryType,
        content: str,
        summary: str,
        confidence: float = 1.0,
        source: str = "manual",
    ) -> Memory:
        """写入一条 Agent 记忆。"""

        agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
        self.identity.assert_org_access(actor_user_id, agent.org_id, Permission.AGENT_CREATE)

        memory = Memory(
            memory_id=new_id("mem"),
            org_id=agent.org_id,
            agent_id=agent.agent_id,
            user_id=actor_user_id,
            memory_type=memory_type,
            content=content.strip(),
            summary=summary.strip() or content.strip()[:200],
            confidence=max(0.0, min(1.0, confidence)),
            source=source,
        )
        self.memories_by_id[memory.memory_id] = memory
        return memory

    def recall_memories(
        self,
        actor_user_id: str,
        agent_id: str,
        query: str,
        limit: int = 5,
    ) -> list[Memory]:
        """召回 Agent 记忆。"""

        agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
        self.identity.assert_org_access(actor_user_id, agent.org_id, Permission.ORGANIZATION_READ)

        # query_terms 是简单关键词集合，后续替换为 embedding query。
        query_terms = {term for term in query.lower().split() if term}

        candidates = [
            memory
            for memory in self.memories_by_id.values()
            if memory.org_id == agent.org_id and memory.agent_id == agent.agent_id
        ]

        scored = [
            (self._score_memory(memory=memory, query_terms=query_terms), memory)
            for memory in candidates
        ]
        filtered = [(score, memory) for score, memory in scored if score > 0 or not query_terms]
        ordered = sorted(filtered, key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [memory for _, memory in ordered[:limit]]

    def _score_memory(self, memory: Memory, query_terms: set[str]) -> float:
        """计算关键词召回分数。"""

        if not query_terms:
            return memory.confidence

        searchable_text = f"{memory.content} {memory.summary}".lower()

        # hit_count 是命中的 query term 数量。
        hit_count = sum(1 for term in query_terms if term in searchable_text)
        return hit_count * memory.confidence


# memory_store 是 MVP 阶段的进程内 Memory Store。
memory_store = MemoryStore(identity=identity_store, agents=agent_store)

