"""知识库 API Schema。"""

from pydantic import BaseModel


class KnowledgeBaseCreateRequest(BaseModel):
    actor_user_id: str
    org_id: str
    name: str
    description: str = ""


class KnowledgeBaseResponse(BaseModel):
    kb_id: str
    org_id: str
    name: str
    description: str
    created_by: str


class DocumentUploadRequest(BaseModel):
    actor_user_id: str
    title: str
    content: str
    chunk_size: int = 500
    chunk_overlap: int = 0


class DocumentResponse(BaseModel):
    document_id: str
    kb_id: str
    org_id: str
    title: str
    status: str
    created_by: str


class ChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    sequence: int
    estimated_tokens: int
    embedding_model: str = ""
    vector_indexed: bool = False
    similarity_score: float | None = None


class SearchRequest(BaseModel):
    actor_user_id: str
    query: str
    limit: int = 5
