"""知识库领域模型。

RAG MVP 的核心是把文档切分成 Chunk，支持关键词检索 fallback，
后续替换为 pgvector 向量检索。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from apps.api.app.domain.identity import utc_now


class DocumentStatus(StrEnum):
    """文档索引状态。"""

    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"


@dataclass(slots=True)
class KnowledgeBase:
    """知识库实体。"""

    # kb_id 是知识库唯一标识。
    kb_id: str

    # org_id 是知识库所属组织。
    org_id: str

    # name 是知识库名称。
    name: str

    # description 是知识库描述。
    description: str

    # created_by 是创建者用户 ID。
    created_by: str

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Document:
    """文档实体。"""

    # document_id 是文档唯一标识。
    document_id: str

    # kb_id 是文档所属知识库。
    kb_id: str

    # org_id 是文档所属组织。
    org_id: str

    # title 是文档标题。
    title: str

    # content 是文档原始内容。
    content: str

    # status 是文档索引状态。
    status: DocumentStatus = DocumentStatus.PENDING

    # created_by 是创建者用户 ID。
    created_by: str = ""

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Chunk:
    """文档切分块。"""

    # chunk_id 是切分块唯一标识。
    chunk_id: str

    # document_id 是所属文档。
    document_id: str

    # kb_id 是所属知识库。
    kb_id: str

    # org_id 是所属组织。
    org_id: str

    # content 是切分块内容。
    content: str

    # sequence 是切分块在文档内的序号。
    sequence: int

    # estimated_tokens 是粗略 token 估算。
    estimated_tokens: int = 0
