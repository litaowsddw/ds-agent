from datetime import datetime
from types import SimpleNamespace

from app.services.memory_vector import MemoryVectorService


class FakeEmbeddingProvider:
    dimension = 2

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FakeVectorIndex:
    def __init__(self) -> None:
        self.chunks = []

    def upsert_chunks(self, chunks):
        self.chunks.extend(chunks)

    def delete_document(self, document_id: str) -> None:
        return None

    def search(self, org_id: str, kb_id: str, query_embedding: list[float], limit: int):
        return []


def test_session_summary_is_written_to_an_agent_scoped_vector_namespace() -> None:
    index = FakeVectorIndex()
    service = MemoryVectorService(FakeEmbeddingProvider(), index)
    memory = SimpleNamespace(
        memory_id="mem_1",
        org_id="org_1",
        agent_id="agent_1",
        content="The user prefers concise Chinese answers.",
        summary="concise Chinese",
    )

    service.upsert(memory)

    assert len(index.chunks) == 1
    assert index.chunks[0].chunk_id == "memory:mem_1"
    assert index.chunks[0].kb_id == "__agent_memory__:agent_1"


def test_lexical_fallback_only_returns_memories_matching_the_user_input() -> None:
    memories = [
        SimpleNamespace(
            summary="Redis deployment notes",
            content="Redis is on port 6379.",
            created_at=datetime(2026, 1, 1),
        ),
        SimpleNamespace(
            summary="Travel plan",
            content="Visit Hangzhou in autumn.",
            created_at=datetime(2026, 1, 2),
        ),
    ]

    recalled = MemoryVectorService._lexical_fallback(memories, "Redis 端口", limit=5)

    assert recalled == [memories[0]]
