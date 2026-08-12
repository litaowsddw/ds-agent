"""知识库与 RAG API（数据库版本）。

使用 SQLAlchemy 异步数据库服务 + Milvus 向量检索。
"""

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.core.auth import AuthenticatedUser, resolve_actor, CurrentUser
from app.models.workflow import KnowledgeBaseModel, DocumentModel, ChunkModel
from app.schemas.knowledge import (
    ChunkResponse,
    DocumentResponse,
    DocumentUploadRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseResponse,
    SearchRequest,
)
from app.services.db.workflow_db import knowledge_base_db, document_db, chunk_db
from app.services.db.identity_db import membership_db
from app.domain.identity import new_id
from app.services.knowledge_vector_index import (
    EmbeddedChunk,
    EmbeddingProvider,
    VectorIndex,
    build_embedding_provider_from_env,
    build_vector_index_from_env,
)
from app.services.document_parser import document_parser

router = APIRouter()

# 全局向量索引和 Embedding Provider
_embedding_provider: EmbeddingProvider | None = None
_vector_index: VectorIndex | None = None


def _get_embedding_provider() -> EmbeddingProvider:
    """获取或创建 Embedding Provider。"""
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = build_embedding_provider_from_env()
    return _embedding_provider


def _get_vector_index() -> VectorIndex:
    """获取或创建向量索引。"""
    global _vector_index
    if _vector_index is None:
        provider = _get_embedding_provider()
        _vector_index = build_vector_index_from_env(
            embedding_dimension=provider.dimension
        )
    return _vector_index


@router.post("", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    request: KnowledgeBaseCreateRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeBaseResponse:
    """创建知识库。"""
    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=request.org_id
        )
        kb = await knowledge_base_db.create_kb(
            session,
            kb_id=new_id("kb"),
            org_id=request.org_id,
            name=request.name,
            description=request.description,
            embedding_model=_get_embedding_provider().model_name,
            created_by=actor_user_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_kb_response(kb)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    auth: AuthenticatedUser,
    org_id: str = Query(description="组织 ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[KnowledgeBaseResponse]:
    """列出组织内的知识库。"""
    try:
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=org_id
        )
        kbs, _ = await knowledge_base_db.list_org_kbs(session, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [_to_kb_response(kb) for kb in kbs]


@router.post("/{kb_id}/documents", response_model=DocumentResponse)
async def upload_document(
    kb_id: str,
    request: DocumentUploadRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    """上传文档并自动切分索引。"""
    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        kb = await knowledge_base_db.get_by_id_required(session, kb_id, "kb_id")
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=kb.org_id
        )

        doc = await document_db.create_document(
            session,
            document_id=new_id("doc"),
            kb_id=kb_id,
            title=request.title,
            content=request.content,
            created_by=actor_user_id,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        # 切分和索引
        await _index_document(
            session,
            doc,
            kb,
            request.chunk_size,
            request.chunk_overlap,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_doc_response(doc)


@router.post("/{kb_id}/documents/upload", response_model=DocumentResponse)
async def upload_document_file(
    kb_id: str,
    auth: CurrentUser,
    actor_user_id: str = Form(default="", description="操作用户 ID（开发降级）"),
    chunk_size: int = Form(default=800, description="切片长度"),
    chunk_overlap: int = Form(default=100, description="切片重叠长度"),
    file: UploadFile = File(description="待上传知识库文件"),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    """上传文件并解析为知识库文档。"""
    try:
        import asyncio

        payload = await file.read()
        parsed = await asyncio.to_thread(
            document_parser.parse, filename=file.filename or "document.txt", payload=payload
        )

        resolved_actor = resolve_actor(auth, actor_user_id)
        kb = await knowledge_base_db.get_by_id_required(session, kb_id, "kb_id")
        await membership_db.assert_org_access(
            session, user_id=resolved_actor, org_id=kb.org_id
        )

        doc = await document_db.create_document(
            session,
            document_id=new_id("doc"),
            kb_id=kb_id,
            title=parsed.title,
            content=parsed.content,
            created_by=resolved_actor,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        await _index_document(session, doc, kb, chunk_size, chunk_overlap)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_doc_response(doc)


@router.get("/{kb_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    kb_id: str,
    auth: AuthenticatedUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[DocumentResponse]:
    """列出知识库内的文档。"""
    try:
        kb = await knowledge_base_db.get_by_id_required(session, kb_id, "kb_id")
        await membership_db.assert_org_access(
            session, user_id=auth.user_id, org_id=kb.org_id
        )
        docs, _ = await document_db.list_kb_documents(session, kb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_to_doc_response(doc) for doc in docs]


@router.post("/{kb_id}/search", response_model=list[ChunkResponse])
async def search_knowledge_base(
    kb_id: str,
    request: SearchRequest,
    auth: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> list[ChunkResponse]:
    """检索知识库（向量 + 关键词混合检索）。"""
    try:
        actor_user_id = resolve_actor(auth, request.actor_user_id)
        kb = await knowledge_base_db.get_by_id_required(session, kb_id, "kb_id")
        await membership_db.assert_org_access(
            session, user_id=actor_user_id, org_id=kb.org_id
        )

        # 尝试向量检索（embedding 计算是同步阻塞 I/O，移出事件循环）
        import asyncio

        provider = _get_embedding_provider()
        index = _get_vector_index()
        query_embedding = (await asyncio.to_thread(provider.embed_texts, [request.query]))[0]
        vector_hits = index.search(
            org_id=kb.org_id,
            kb_id=kb_id,
            query_embedding=query_embedding,
            limit=request.limit,
        )

        if vector_hits:
            # 从数据库加载命中的 chunk
            hit_ids = [hit.chunk_id for hit in vector_hits]
            results = []
            for hit in vector_hits:
                chunk_model = await chunk_db.get_by_id(session, hit.chunk_id, "chunk_id")
                if chunk_model is not None:
                    results.append(_to_chunk_response_from_model(chunk_model, hit.score))
            return results

        # 降级到关键词检索
        return await _keyword_search(session, kb_id, request.query, request.limit)

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _index_document(
    session: AsyncSession,
    doc: DocumentModel,
    kb: KnowledgeBaseModel,
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    """切分文档并索引到 Milvus。"""
    # 文本切分
    chunk_parts = _split_text(doc.content, chunk_size, chunk_overlap)
    if not chunk_parts:
        await document_db.update_status(session, doc.document_id, "failed")
        return

    # 生成 Embedding（同步阻塞 I/O，移出事件循环）
    import asyncio

    provider = _get_embedding_provider()
    embeddings = await asyncio.to_thread(provider.embed_texts, chunk_parts)

    # 创建 Chunk 记录
    index = _get_vector_index()
    embedded_chunks: list[EmbeddedChunk] = []

    for seq, part in enumerate(chunk_parts):
        chunk = await chunk_db.create_chunk(
            session,
            chunk_id=new_id("chk"),
            document_id=doc.document_id,
            content=part,
            sequence=seq,
            estimated_tokens=max(1, len(part) // 4),
            embedding_model=provider.model_name,
        )
        embedded_chunks.append(
            EmbeddedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                kb_id=kb.kb_id,
                org_id=kb.org_id,
                content=chunk.content,
                sequence=chunk.sequence,
                estimated_tokens=chunk.estimated_tokens,
                embedding=embeddings[seq],
            )
        )

    # 索引到 Milvus
    index.delete_document(document_id=doc.document_id)
    index.upsert_chunks(embedded_chunks)
    for chunk in embedded_chunks:
        await chunk_db.mark_vector_indexed(session, chunk.chunk_id)

    # 更新文档状态
    await document_db.update_status(session, doc.document_id, "indexed")


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """按固定长度切片。"""
    normalized_chunk_size = max(50, min(int(chunk_size or 500), 4000))
    normalized_overlap = max(0, min(int(chunk_overlap or 0), normalized_chunk_size // 2))
    step = normalized_chunk_size - normalized_overlap
    stripped_text = text.strip()
    if not stripped_text:
        return []

    chunks: list[str] = []
    for start in range(0, len(stripped_text), step):
        part = stripped_text[start : start + normalized_chunk_size].strip()
        if part:
            chunks.append(part)
        if start + normalized_chunk_size >= len(stripped_text):
            break
    return chunks


async def _keyword_search(
    session: AsyncSession,
    kb_id: str,
    query: str,
    limit: int,
) -> list[ChunkResponse]:
    """关键词检索降级方案。"""
    from sqlalchemy import select
    from app.models.workflow import ChunkModel, DocumentModel as WFDocumentModel

    query_terms = {t for t in query.lower().split() if t}
    stmt = (
        select(ChunkModel)
        .join(WFDocumentModel, ChunkModel.document_id == WFDocumentModel.document_id)
        .where(WFDocumentModel.kb_id == kb_id)
    )
    result = await session.execute(stmt)
    all_chunks = list(result.scalars().all())

    if not query_terms:
        return [_to_chunk_response_from_model(c, 0.0) for c in all_chunks[:limit]]

    scored: list[tuple[float, ChunkModel]] = []
    for chunk in all_chunks:
        text = chunk.content.lower()
        score = sum(1 for t in query_terms if t in text)
        if score > 0:
            scored.append((float(score), chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_to_chunk_response_from_model(chunk, score) for score, chunk in scored[:limit]]


def _to_kb_response(kb: KnowledgeBaseModel) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        kb_id=kb.kb_id,
        org_id=kb.org_id,
        name=kb.name,
        description=kb.description or "",
        created_by=kb.created_by,
    )


def _to_doc_response(doc: DocumentModel) -> DocumentResponse:
    return DocumentResponse(
        document_id=doc.document_id,
        kb_id=doc.kb_id,
        org_id="",
        title=doc.title,
        status=doc.status,
        created_by=doc.created_by,
    )


def _to_chunk_response_from_model(chunk: ChunkModel, similarity_score: float | None) -> ChunkResponse:
    return ChunkResponse(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        content=chunk.content,
        sequence=chunk.sequence,
        estimated_tokens=chunk.estimated_tokens,
        embedding_model=chunk.embedding_model or "",
        vector_indexed=chunk.vector_indexed,
        similarity_score=similarity_score,
    )
