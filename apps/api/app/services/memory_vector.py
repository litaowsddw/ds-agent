"""Persistent Agent memory recall backed by the configured vector database."""

from __future__ import annotations

import re

from app.models.runtime import MemoryModel
from app.services.knowledge_vector_index import (
    EmbeddedChunk,
    EmbeddingProvider,
    VectorIndex,
    build_embedding_provider_from_env,
    build_vector_index_from_env,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class MemoryVectorService:
    """Store compressed memories as isolated vector chunks and recall by query."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        vector_index: VectorIndex | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_index = vector_index

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            self._embedding_provider = build_embedding_provider_from_env()
        return self._embedding_provider

    @property
    def vector_index(self) -> VectorIndex:
        if self._vector_index is None:
            self._vector_index = build_vector_index_from_env(self.embedding_provider.dimension)
        return self._vector_index

    def upsert(self, memory: MemoryModel) -> None:
        """Write a memory summary into Milvus (or the configured fallback index)."""

        content = str(memory.content or memory.summary or "").strip()
        if not content:
            return
        self.vector_index.upsert_chunks(
            [
                EmbeddedChunk(
                    chunk_id=self._chunk_id(memory.memory_id),
                    document_id=memory.memory_id,
                    kb_id=self._memory_namespace(memory.agent_id),
                    org_id=memory.org_id,
                    content=content,
                    sequence=0,
                    estimated_tokens=max(1, len(content) // 4),
                    embedding=self.embedding_provider.embed_texts([content])[0],
                )
            ]
        )

    async def recall(
        self,
        session: AsyncSession,
        *,
        org_id: str,
        agent_id: str,
        query: str,
        limit: int = 5,
    ) -> list[MemoryModel]:
        """Return only memories relevant to the current user input.

        The lexical fallback is used only when the vector backend has no hit
        (for example, a local in-memory index after process restart). Production
        Milvus remains the primary retrieval path.
        """

        try:
            query_embedding = self.embedding_provider.embed_texts([query])[0]
            hits = self.vector_index.search(
                org_id=org_id,
                kb_id=self._memory_namespace(agent_id),
                query_embedding=query_embedding,
                limit=limit,
            )
        except Exception:
            hits = []
        memory_ids = [self._memory_id(hit.chunk_id) for hit in hits]
        memory_ids = [memory_id for memory_id in memory_ids if memory_id]
        if memory_ids:
            rows = await session.scalars(
                select(MemoryModel).where(
                    MemoryModel.agent_id == agent_id,
                    MemoryModel.org_id == org_id,
                    MemoryModel.memory_id.in_(memory_ids),
                )
            )
            by_id = {row.memory_id: row for row in rows}
            return [by_id[memory_id] for memory_id in memory_ids if memory_id in by_id]

        rows = await session.scalars(
            select(MemoryModel).where(
                MemoryModel.agent_id == agent_id,
                MemoryModel.org_id == org_id,
            )
        )
        return self._lexical_fallback(list(rows), query, limit)

    @staticmethod
    def _memory_namespace(agent_id: str) -> str:
        return f"__agent_memory__:{agent_id}"

    @staticmethod
    def _chunk_id(memory_id: str) -> str:
        return f"memory:{memory_id}"

    @staticmethod
    def _memory_id(chunk_id: str) -> str:
        return chunk_id.removeprefix("memory:") if chunk_id.startswith("memory:") else ""

    @staticmethod
    def _lexical_fallback(
        memories: list[MemoryModel], query: str, limit: int
    ) -> list[MemoryModel]:
        terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{1,}", query.lower()))
        if not terms:
            return []
        scored: list[tuple[int, MemoryModel]] = []
        for memory in memories:
            haystack = f"{memory.summary}\n{memory.content}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, memory))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [memory for _, memory in scored[:limit]]


memory_vector_service = MemoryVectorService()
