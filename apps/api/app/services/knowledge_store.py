"""知识库与 RAG 检索服务。

MVP 使用内存存储和关键词检索。后续替换为 pgvector 向量检索。
"""

from apps.api.app.domain.identity import new_id
from apps.api.app.domain.knowledge import (
    Chunk,
    Document,
    DocumentStatus,
    KnowledgeBase,
)
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission
from apps.api.app.storage.local_state import local_state_store


class KnowledgeStore:
    """管理知识库、文档和 Chunk。"""

    def __init__(self, identity: IdentityStore) -> None:
        self.identity = identity
        self.kbs_by_id: dict[str, KnowledgeBase] = {}
        self.documents_by_id: dict[str, Document] = {}
        self.chunks_by_id: dict[str, Chunk] = {}
        self._load_state()

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
        self._index_document(doc, chunk_size=chunk_size)
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
        query_terms = {t for t in query.lower().split() if t}
        candidates = [c for c in self.chunks_by_id.values() if c.kb_id == kb_id]
        if not query_terms:
            return candidates[:limit]
        scored = []
        for chunk in candidates:
            text = chunk.content.lower()
            score = sum(1 for t in query_terms if t in text)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:limit]]

    def _index_document(self, doc: Document, chunk_size: int) -> None:
        """把文档切分成 Chunk。"""
        text = doc.content
        seq = 0
        for i in range(0, len(text), chunk_size):
            part = text[i : i + chunk_size]
            chunk = Chunk(
                chunk_id=new_id("chk"),
                document_id=doc.document_id,
                kb_id=doc.kb_id,
                org_id=doc.org_id,
                content=part,
                sequence=seq,
                estimated_tokens=max(1, len(part) // 4),
            )
            self.chunks_by_id[chunk.chunk_id] = chunk
            seq += 1
        doc.status = DocumentStatus.INDEXED

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
