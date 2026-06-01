"""知识库与 RAG 检索服务。

MVP 使用内存存储和关键词检索。后续替换为 pgvector 向量检索。
"""

from dataclasses import replace

from apps.api.app.domain.identity import new_id
from apps.api.app.domain.knowledge import (
    Chunk,
    Document,
    DocumentStatus,
    KnowledgeBase,
)
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.knowledge_vector_index import (
    EmbeddedChunk,
    EmbeddingProvider,
    VectorIndex,
    build_embedding_provider_from_env,
    build_vector_index_from_env,
)
from apps.api.app.services.rbac import Permission
from apps.api.app.storage.local_state import local_state_store


class KnowledgeStore:
    """管理知识库、文档和 Chunk。"""

    def __init__(
        self,
        identity: IdentityStore,
        embedding_provider: EmbeddingProvider | None = None,
        vector_index: VectorIndex | None = None,
    ) -> None:
        self.identity = identity
        self.kbs_by_id: dict[str, KnowledgeBase] = {}
        self.documents_by_id: dict[str, Document] = {}
        self.chunks_by_id: dict[str, Chunk] = {}
        self.embedding_provider = embedding_provider or build_embedding_provider_from_env()
        self.vector_index = vector_index or build_vector_index_from_env(
            embedding_dimension=self.embedding_provider.dimension
        )
        self._load_state()
        self._rebuild_vector_index_from_loaded_chunks()

    def create_knowledge_base(
        self,
        actor_user_id: str,
        org_id: str,
        name: str,
        description: str,
    ) -> KnowledgeBase:
        """创建知识库。"""
        self.identity.assert_org_access(actor_user_id, org_id, Permission.AGENT_CREATE)
        kb = KnowledgeBase(
            kb_id=new_id("kb"),
            org_id=org_id,
            name=name.strip(),
            description=description.strip(),
            created_by=actor_user_id,
        )
        self.kbs_by_id[kb.kb_id] = kb
        self._save_state()
        return kb

    def list_knowledge_bases(self, actor_user_id: str, org_id: str) -> list[KnowledgeBase]:
        """列出组织内的知识库。"""
        self.identity.assert_org_access(actor_user_id, org_id, Permission.ORGANIZATION_READ)
        return sorted(
            [kb for kb in self.kbs_by_id.values() if kb.org_id == org_id],
            key=lambda kb: kb.name,
        )

    def upload_document(
        self,
        actor_user_id: str,
        kb_id: str,
        title: str,
        content: str,
        chunk_size: int = 500,
        chunk_overlap: int = 0,
    ) -> Document:
        """上传文档并自动切分。"""
        kb = self._require_kb(kb_id)
        self.identity.assert_org_access(actor_user_id, kb.org_id, Permission.AGENT_CREATE)
        doc = Document(
            document_id=new_id("doc"),
            kb_id=kb.kb_id,
            org_id=kb.org_id,
            title=title.strip(),
            content=content,
            created_by=actor_user_id,
        )
        self.documents_by_id[doc.document_id] = doc
        self._index_document(doc, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self._save_state()
        return doc

    def list_documents(self, actor_user_id: str, kb_id: str) -> list[Document]:
        """列出知识库内的文档。"""
        kb = self._require_kb(kb_id)
        self.identity.assert_org_access(actor_user_id, kb.org_id, Permission.ORGANIZATION_READ)
        return [doc for doc in self.documents_by_id.values() if doc.kb_id == kb_id]

    def search(
        self,
        actor_user_id: str,
        kb_id: str,
        query: str,
        limit: int = 5,
    ) -> list[Chunk]:
        """关键词检索知识库 Chunk。"""
        kb = self._require_kb(kb_id)
        self.identity.assert_org_access(actor_user_id, kb.org_id, Permission.ORGANIZATION_READ)
        query_embedding = self.embedding_provider.embed_texts([query])[0]
        vector_hits = self.vector_index.search(
            org_id=kb.org_id,
            kb_id=kb_id,
            query_embedding=query_embedding,
            limit=limit,
        )
        if vector_hits:
            return [
                replace(self.chunks_by_id[hit.chunk_id], similarity_score=hit.score)
                for hit in vector_hits
                if hit.chunk_id in self.chunks_by_id
            ]

        return self._keyword_search(kb_id=kb_id, query=query, limit=limit)

    def _keyword_search(self, kb_id: str, query: str, limit: int) -> list[Chunk]:
        """关键词检索回退，避免向量索引不可用或无命中时完全失效。"""

        query_terms = {t for t in query.lower().split() if t}
        candidates = [c for c in self.chunks_by_id.values() if c.kb_id == kb_id]
        if not query_terms:
            return candidates[:limit]

        scored: list[tuple[float, Chunk]] = []
        for chunk in candidates:
            text = chunk.content.lower()
            score = sum(1 for t in query_terms if t in text)
            if score > 0:
                scored.append((float(score), chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [replace(chunk, similarity_score=score) for score, chunk in scored[:limit]]

    def _index_document(self, doc: Document, chunk_size: int, chunk_overlap: int) -> None:
        """把文档切分成 Chunk。"""
        chunk_parts = self._split_text(
            text=doc.content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        embeddings = self.embedding_provider.embed_texts(chunk_parts)
        embedded_chunks: list[EmbeddedChunk] = []
        for seq, part in enumerate(chunk_parts):
            chunk = Chunk(
                chunk_id=new_id("chk"),
                document_id=doc.document_id,
                kb_id=doc.kb_id,
                org_id=doc.org_id,
                content=part,
                sequence=seq,
                estimated_tokens=max(1, len(part) // 4),
                embedding_model=self.embedding_provider.model_name,
                vector_indexed=True,
            )
            self.chunks_by_id[chunk.chunk_id] = chunk
            embedded_chunks.append(
                EmbeddedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    kb_id=chunk.kb_id,
                    org_id=chunk.org_id,
                    content=chunk.content,
                    sequence=chunk.sequence,
                    estimated_tokens=chunk.estimated_tokens,
                    embedding=embeddings[seq],
                )
            )
        self.vector_index.delete_document(document_id=doc.document_id)
        self.vector_index.upsert_chunks(embedded_chunks)
        doc.status = DocumentStatus.INDEXED

    def _split_text(self, text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        """按固定长度切片，支持 overlap，保证上传文档一定能被索引。"""

        normalized_chunk_size = max(50, min(int(chunk_size or 500), 4000))
        normalized_overlap = max(0, min(int(chunk_overlap or 0), normalized_chunk_size // 2))
        step = normalized_chunk_size - normalized_overlap
        stripped_text = text.strip()
        if not stripped_text:
            raise ValueError("文档内容不能为空")

        chunks: list[str] = []
        for start in range(0, len(stripped_text), step):
            part = stripped_text[start : start + normalized_chunk_size].strip()
            if part:
                chunks.append(part)
            if start + normalized_chunk_size >= len(stripped_text):
                break
        return chunks

    def _require_kb(self, kb_id: str) -> KnowledgeBase:
        """要求知识库必须存在。"""
        kb = self.kbs_by_id.get(kb_id)
        if kb is None:
            raise ValueError("知识库不存在")
        return kb

    def _load_state(self) -> None:
        state = local_state_store.load_bucket("knowledge", {})
        if not isinstance(state, dict):
            return
        self.kbs_by_id = state.get("kbs_by_id", self.kbs_by_id)
        self.documents_by_id = state.get("documents_by_id", self.documents_by_id)
        self.chunks_by_id = state.get("chunks_by_id", self.chunks_by_id)
        for chunk in self.chunks_by_id.values():
            if not hasattr(chunk, "embedding_model"):
                chunk.embedding_model = self.embedding_provider.model_name
            if not hasattr(chunk, "vector_indexed"):
                chunk.vector_indexed = False
            if not hasattr(chunk, "similarity_score"):
                chunk.similarity_score = None

    def _rebuild_vector_index_from_loaded_chunks(self) -> None:
        """API 重启后用本地 Chunk 元数据重建向量索引。"""

        if not self.chunks_by_id:
            return

        chunks = list(self.chunks_by_id.values())
        embeddings = self.embedding_provider.embed_texts([chunk.content for chunk in chunks])
        document_ids = {chunk.document_id for chunk in chunks}
        for document_id in document_ids:
            self.vector_index.delete_document(document_id=document_id)

        embedded_chunks = [
            EmbeddedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                kb_id=chunk.kb_id,
                org_id=chunk.org_id,
                content=chunk.content,
                sequence=chunk.sequence,
                estimated_tokens=chunk.estimated_tokens,
                embedding=embeddings[index],
            )
            for index, chunk in enumerate(chunks)
        ]
        self.vector_index.upsert_chunks(embedded_chunks)
        for chunk in chunks:
            chunk.embedding_model = self.embedding_provider.model_name
            chunk.vector_indexed = True

    def _save_state(self) -> None:
        local_state_store.save_bucket(
            "knowledge",
            {
                "kbs_by_id": self.kbs_by_id,
                "documents_by_id": self.documents_by_id,
                "chunks_by_id": self.chunks_by_id,
            },
        )


knowledge_store = KnowledgeStore(identity=identity_store)
