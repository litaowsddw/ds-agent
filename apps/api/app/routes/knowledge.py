"""知识库与 RAG API。"""

from fastapi import APIRouter, HTTPException, Query

from apps.api.app.domain.knowledge import Chunk, Document, KnowledgeBase
from apps.api.app.schemas.knowledge import (
    ChunkResponse,
    DocumentResponse,
    DocumentUploadRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseResponse,
    SearchRequest,
)
from apps.api.app.services.knowledge_store import knowledge_store

router = APIRouter()


@router.post("", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    request: KnowledgeBaseCreateRequest,
) -> KnowledgeBaseResponse:
    """创建知识库。"""
    try:
        kb = knowledge_store.create_knowledge_base(
            actor_user_id=request.actor_user_id,
            org_id=request.org_id,
            name=request.name,
            description=request.description,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_kb_response(kb)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    org_id: str = Query(description="组织 ID"),
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[KnowledgeBaseResponse]:
    """列出组织内的知识库。"""
    try:
        kbs = knowledge_store.list_knowledge_bases(actor_user_id=actor_user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [_to_kb_response(kb) for kb in kbs]


@router.post("/{kb_id}/documents", response_model=DocumentResponse)
async def upload_document(kb_id: str, request: DocumentUploadRequest) -> DocumentResponse:
    """上传文档。"""
    try:
        doc = knowledge_store.upload_document(
            actor_user_id=request.actor_user_id,
            kb_id=kb_id,
            title=request.title,
            content=request.content,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_doc_response(doc)


@router.get("/{kb_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    kb_id: str,
    actor_user_id: str = Query(description="操作者用户 ID"),
) -> list[DocumentResponse]:
    """列出知识库内的文档。"""
    try:
        docs = knowledge_store.list_documents(actor_user_id=actor_user_id, kb_id=kb_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_to_doc_response(doc) for doc in docs]


@router.post("/{kb_id}/search", response_model=list[ChunkResponse])
async def search_knowledge_base(kb_id: str, request: SearchRequest) -> list[ChunkResponse]:
    """检索知识库。"""
    try:
        chunks = knowledge_store.search(
            actor_user_id=request.actor_user_id,
            kb_id=kb_id,
            query=request.query,
            limit=request.limit,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_to_chunk_response(c) for c in chunks]


def _to_kb_response(kb: KnowledgeBase) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        kb_id=kb.kb_id,
        org_id=kb.org_id,
        name=kb.name,
        description=kb.description,
        created_by=kb.created_by,
    )


def _to_doc_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        document_id=doc.document_id,
        kb_id=doc.kb_id,
        org_id=doc.org_id,
        title=doc.title,
        status=doc.status,
        created_by=doc.created_by,
    )


def _to_chunk_response(chunk: Chunk) -> ChunkResponse:
    return ChunkResponse(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        content=chunk.content,
        sequence=chunk.sequence,
        estimated_tokens=chunk.estimated_tokens,
        embedding_model=chunk.embedding_model,
        vector_indexed=chunk.vector_indexed,
        similarity_score=chunk.similarity_score,
    )
