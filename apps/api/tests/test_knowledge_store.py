"""知识库与 RAG 检索测试。"""

from apps.api.app.services.identity_store import IdentityStore
from apps.api.app.services.knowledge_store import KnowledgeStore
from apps.api.app.services.knowledge_vector_index import EmbeddedChunk, InMemoryVectorIndex


class RecordingVectorIndex(InMemoryVectorIndex):
    """测试用向量索引，记录写入 Milvus 等价索引的数据。"""

    def __init__(self) -> None:
        super().__init__()
        self.upserted_chunks: list[EmbeddedChunk] = []

    def upsert_chunks(self, chunks: list[EmbeddedChunk]) -> None:
        self.upserted_chunks.extend(chunks)
        super().upsert_chunks(chunks)


def _setup() -> tuple[KnowledgeStore, str, str]:
    """创建测试用的 Store 和用户/组织。"""
    identity = IdentityStore()
    user = identity.register_user(email="rag@test.com", display_name="RAG", password="pass")
    org = identity.create_organization(creator_user_id=user.user_id, name="RAG Org")
    ks = KnowledgeStore(identity=identity)
    return ks, user.user_id, org.org_id


def test_create_knowledge_base_and_upload_document() -> None:
    """创建知识库并上传文档后应可检索到相关 Chunk。"""
    ks, uid, oid = _setup()

    kb = ks.create_knowledge_base(
        actor_user_id=uid,
        org_id=oid,
        name="测试知识库",
        description="测试用",
    )
    assert kb.kb_id.startswith("kb_")
    assert kb.org_id == oid

    kbs = ks.list_knowledge_bases(actor_user_id=uid, org_id=oid)
    assert len(kbs) == 1

    doc = ks.upload_document(
        actor_user_id=uid,
        kb_id=kb.kb_id,
        title="测试文档",
        content="Python 是一门编程语言。它支持面向对象编程。",
        chunk_size=20,
        chunk_overlap=5,
    )
    assert doc.status == "indexed"

    docs = ks.list_documents(actor_user_id=uid, kb_id=kb.kb_id)
    assert len(docs) == 1

    results = ks.search(
        actor_user_id=uid,
        kb_id=kb.kb_id,
        query="Python 编程",
        limit=3,
    )
    assert len(results) > 0
    assert any("Python" in c.content for c in results)
    assert all(c.vector_indexed for c in results)
    assert all(c.embedding_model for c in results)
    assert results[0].similarity_score is not None


def test_search_returns_empty_for_unrelated_query() -> None:
    """不相关的查询应返回空结果。"""
    ks, uid, oid = _setup()

    kb = ks.create_knowledge_base(
        actor_user_id=uid,
        org_id=oid,
        name="空检索测试",
        description="",
    )
    ks.upload_document(
        actor_user_id=uid,
        kb_id=kb.kb_id,
        title="文档",
        content="这是一段关于机器学习的内容",
        chunk_size=50,
    )
    results = ks.search(
        actor_user_id=uid,
        kb_id=kb.kb_id,
        query="量子力学",
        limit=5,
    )
    assert len(results) == 0


def test_upload_document_writes_embeddings_to_vector_index() -> None:
    """上传文档后应切片、生成 embedding，并写入向量索引。"""

    identity = IdentityStore()
    user = identity.register_user(email="vector@test.com", display_name="Vector", password="pass")
    org = identity.create_organization(creator_user_id=user.user_id, name="Vector Org")
    vector_index = RecordingVectorIndex()
    ks = KnowledgeStore(identity=identity, vector_index=vector_index)
    kb = ks.create_knowledge_base(user.user_id, org.org_id, "Vector KB", "")

    ks.upload_document(
        actor_user_id=user.user_id,
        kb_id=kb.kb_id,
        title="Vector Doc",
        content="Milvus 支持海量向量检索。AgentFlow 上传文档后会生成 embedding。",
        chunk_size=50,
        chunk_overlap=10,
    )

    assert len(vector_index.upserted_chunks) >= 1
    assert len(vector_index.upserted_chunks[0].embedding) == ks.embedding_provider.dimension
    assert vector_index.upserted_chunks[0].kb_id == kb.kb_id
    assert vector_index.upserted_chunks[0].org_id == org.org_id
