"""知识库向量索引服务。

该模块把 embedding 生成与向量数据库访问从 KnowledgeStore 中拆出来。生产环境使用 Milvus，
测试和本地无 Milvus 服务时使用内存向量索引，保证文档上传、切片、检索链路始终可验证。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(slots=True)
class EmbeddedChunk:
    """待写入向量索引的 Chunk 数据。"""

    # chunk_id 是业务侧 Chunk 主键，同时作为 Milvus 主键。
    chunk_id: str

    # document_id 用于按文档重建索引时清理旧向量。
    document_id: str

    # kb_id 是知识库隔离字段，检索时会作为向量过滤条件。
    kb_id: str

    # org_id 是组织隔离字段，防止跨租户检索。
    org_id: str

    # content 是原始切片文本，Milvus 中保留一份用于调试和后续混合检索。
    content: str

    # sequence 是切片在文档内的顺序。
    sequence: int

    # estimated_tokens 是粗略 token 数，用于上下文预算。
    estimated_tokens: int

    # embedding 是归一化后的向量，当前默认维度由 EmbeddingProvider 决定。
    embedding: list[float]


@dataclass(slots=True)
class VectorSearchHit:
    """向量检索命中结果。"""

    # chunk_id 是命中的 Chunk 主键。
    chunk_id: str

    # score 是相似度分数；当前使用归一化向量内积，越大越相似。
    score: float


class EmbeddingProvider(Protocol):
    """Embedding 生成器协议。"""

    # model_name 是写入 Chunk 元数据的 embedding 模型名。
    model_name: str

    # dimension 是向量维度，必须与 Milvus collection schema 保持一致。
    dimension: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量。"""


class VectorIndex(Protocol):
    """向量索引协议。"""

    def upsert_chunks(self, chunks: list[EmbeddedChunk]) -> None:
        """写入或更新 Chunk 向量。"""

    def delete_document(self, document_id: str) -> None:
        """删除某个文档下的全部 Chunk 向量。"""

    def search(
        self,
        org_id: str,
        kb_id: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[VectorSearchHit]:
        """按组织和知识库过滤后执行向量检索。"""


class DeterministicEmbeddingProvider:
    """确定性轻量 embedding。

    该实现不依赖外部模型服务，适合 MVP、本地开发和单元测试。它用词项 hash 投影生成归一化稀疏向量，
    后续可以替换为 OpenAI、DeepSeek、Ollama 或企业私有 embedding 服务。
    """

    def __init__(self, dimension: int = 256, model_name: str = "local-hash-embedding-v1") -> None:
        # dimension 是向量维度；Milvus collection 创建后不可随意修改。
        self.dimension = dimension

        # model_name 写入 Chunk，便于后续判断是否需要重建索引。
        self.model_name = model_name

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """把文本列表转换为归一化向量列表。"""

        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        """生成单条文本向量。"""

        vector = [0.0 for _ in range(self.dimension)]
        for token in self._tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def _tokenize(self, text: str) -> list[str]:
        """分词：英文按词切分，中文保留连续片段并增加二字滑窗。"""

        normalized_text = text.lower().strip()
        rough_terms = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", normalized_text)
        tokens: list[str] = []
        for term in rough_terms:
            tokens.append(term)
            if re.fullmatch(r"[\u4e00-\u9fff]+", term) and len(term) > 2:
                tokens.extend(term[index : index + 2] for index in range(len(term) - 1))
        return tokens


class OllamaEmbeddingProvider:
    """Embedding provider backed by a local Ollama server."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model_name: str = "bge-m3:latest",
        dimension: int = 1024,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.dimension = dimension
        self.timeout_seconds = timeout_seconds

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        payload = {"model": self.model_name, "prompt": text}
        request = Request(
            url=f"{self.base_url}/api/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama embedding HTTP {exc.code}: {detail[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Ollama embedding network error: {exc.reason}") from exc

        embedding = body.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError("Ollama embedding response missing embedding list")
        vector = [float(value) for value in embedding]
        if len(vector) != self.dimension:
            raise RuntimeError(
                f"Ollama embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
            )
        return self._normalize(vector)

    def _normalize(self, vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class InMemoryVectorIndex:
    """内存向量索引，用于测试和无 Milvus 环境的本地回退。"""

    def __init__(self, min_score: float = 0.05) -> None:
        # vectors_by_chunk_id 保存向量与过滤元数据。
        self.vectors_by_chunk_id: dict[str, EmbeddedChunk] = {}

        # min_score 是最低相似度阈值，避免完全无关查询返回噪声。
        self.min_score = min_score

    def upsert_chunks(self, chunks: list[EmbeddedChunk]) -> None:
        """写入 Chunk 向量。"""

        for chunk in chunks:
            self.vectors_by_chunk_id[chunk.chunk_id] = chunk

    def delete_document(self, document_id: str) -> None:
        """删除文档向量。"""

        removable_chunk_ids = [
            chunk_id
            for chunk_id, chunk in self.vectors_by_chunk_id.items()
            if chunk.document_id == document_id
        ]
        for chunk_id in removable_chunk_ids:
            del self.vectors_by_chunk_id[chunk_id]

    def search(
        self,
        org_id: str,
        kb_id: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[VectorSearchHit]:
        """执行内存余弦检索。"""

        hits: list[VectorSearchHit] = []
        for chunk in self.vectors_by_chunk_id.values():
            if chunk.org_id != org_id or chunk.kb_id != kb_id:
                continue
            score = self._dot(query_embedding, chunk.embedding)
            if score >= self.min_score:
                hits.append(VectorSearchHit(chunk_id=chunk.chunk_id, score=score))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]

    def _dot(self, left: list[float], right: list[float]) -> float:
        """计算两个归一化向量的内积。"""

        return sum(a * b for a, b in zip(left, right, strict=False))


class MilvusVectorIndex:
    """Milvus 向量索引实现。"""

    def __init__(
        self,
        host: str,
        port: str,
        collection_name: str,
        dimension: int,
        alias: str = "agentflow_knowledge",
    ) -> None:
        # pymilvus 在未安装依赖的本地测试环境中可能不存在，因此延迟导入。
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

        # alias 是 pymilvus 连接别名，避免与其他 SDK 调用互相覆盖。
        self.alias = alias

        # collection_name 是 Milvus collection 名称。
        self.collection_name = collection_name

        # dimension 必须与 embedding provider 输出一致。
        self.dimension = dimension

        # Collection 类型保存到实例上，便于类型运行时创建 collection。
        self._collection_cls = Collection

        connections.connect(alias=alias, host=host, port=port)

        if not utility.has_collection(collection_name, using=alias):
            fields = [
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
                FieldSchema(name="org_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="kb_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="sequence", dtype=DataType.INT64),
                FieldSchema(name="estimated_tokens", dtype=DataType.INT64),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            ]
            schema = CollectionSchema(
                fields=fields,
                description="AgentFlow knowledge chunk embeddings",
                enable_dynamic_field=False,
            )
            collection = Collection(name=collection_name, schema=schema, using=alias)
            collection.create_index(
                field_name="embedding",
                index_params={
                    "index_type": "HNSW",
                    "metric_type": "IP",
                    "params": {"M": 16, "efConstruction": 128},
                },
            )

        self.collection = Collection(name=collection_name, using=alias)
        self.collection.load()

    def upsert_chunks(self, chunks: list[EmbeddedChunk]) -> None:
        """写入 Chunk 向量到 Milvus。"""

        if not chunks:
            return

        data = [
            [chunk.chunk_id for chunk in chunks],
            [chunk.org_id for chunk in chunks],
            [chunk.kb_id for chunk in chunks],
            [chunk.document_id for chunk in chunks],
            [chunk.sequence for chunk in chunks],
            [chunk.estimated_tokens for chunk in chunks],
            [chunk.content for chunk in chunks],
            [chunk.embedding for chunk in chunks],
        ]
        self.collection.insert(data)
        self.collection.flush()
        self.collection.load()

    def delete_document(self, document_id: str) -> None:
        """从 Milvus 删除文档向量。"""

        expr = f'document_id == "{self._escape_expr_value(document_id)}"'
        self.collection.delete(expr)
        self.collection.flush()

    def search(
        self,
        org_id: str,
        kb_id: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[VectorSearchHit]:
        """执行 Milvus 向量检索。"""

        expr = (
            f'org_id == "{self._escape_expr_value(org_id)}" '
            f'and kb_id == "{self._escape_expr_value(kb_id)}"'
        )
        results = self.collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "IP", "params": {"ef": 64}},
            limit=limit,
            expr=expr,
            output_fields=["chunk_id"],
        )
        hits: list[VectorSearchHit] = []
        for item in results[0]:
            chunk_id = str(item.entity.get("chunk_id"))
            hits.append(VectorSearchHit(chunk_id=chunk_id, score=float(item.score)))
        return hits

    def _escape_expr_value(self, value: str) -> str:
        """转义 Milvus 表达式中的字符串值。"""

        return value.replace("\\", "\\\\").replace('"', '\\"')


class OpenAICompatibleEmbeddingProvider:
    """OpenAI-compatible 语义 embedding provider（如 text-embedding-v4 / ada）。

    与 local-hash 的确定性哈希完全不同：这是真正的语义向量。向量经 L2 归一化，
    与 Milvus IP 度量（归一化后等价 cosine）配合。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        dimension: int,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.dimension = dimension
        self.timeout_seconds = timeout_seconds

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import httpx

        payload = {"model": self.model_name, "input": texts}
        response = httpx.post(
            url=f"{self.base_url}/embeddings",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            detail = response.text[:300]
            raise RuntimeError(f"Embedding HTTP {response.status_code}: {detail}")

        body = response.json()
        data = body.get("data") or []
        # 供应商按 input 顺序返回向量，explicitly sort by index 对齐
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        if len(ordered) != len(texts):
            raise RuntimeError(
                f"Embedding 返回数量不匹配: expect {len(texts)}, got {len(ordered)}"
            )

        vectors: list[list[float]] = []
        for item in ordered:
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise RuntimeError("Embedding 响应缺少 embedding 字段")
            vector = [float(value) for value in embedding]
            if len(vector) != self.dimension:
                raise RuntimeError(
                    f"Embedding 维度不匹配: expect {self.dimension}, got {len(vector)}"
                )
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append(vector if norm == 0 else [value / norm for value in vector])
        return vectors


def build_embedding_provider_from_env() -> EmbeddingProvider:
    """根据环境变量创建 embedding provider。"""

    dimension = int(os.getenv("AGENTFLOW_EMBEDDING_DIMENSION", "256"))
    model_name = os.getenv("AGENTFLOW_EMBEDDING_MODEL", "local-hash-embedding-v1")
    provider = os.getenv("AGENTFLOW_EMBEDDING_PROVIDER", "local-hash").lower()
    if provider == "ollama":
        return OllamaEmbeddingProvider(
            base_url=os.getenv("AGENTFLOW_EMBEDDING_BASE_URL", "http://127.0.0.1:11434"),
            model_name=model_name,
            dimension=dimension,
            timeout_seconds=int(os.getenv("AGENTFLOW_EMBEDDING_TIMEOUT_SECONDS", "30")),
        )
    if provider in ("openai-compatible", "openai_compatible", "openai"):
        api_key = os.getenv("AGENTFLOW_EMBEDDING_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "AGENTFLOW_EMBEDDING_PROVIDER=openai-compatible 需要设置 AGENTFLOW_EMBEDDING_API_KEY"
            )
        return OpenAICompatibleEmbeddingProvider(
            base_url=os.getenv("AGENTFLOW_EMBEDDING_BASE_URL", "").rstrip("/"),
            api_key=api_key,
            model_name=model_name,
            dimension=dimension,
            timeout_seconds=int(os.getenv("AGENTFLOW_EMBEDDING_TIMEOUT_SECONDS", "30")),
        )
    return DeterministicEmbeddingProvider(dimension=dimension, model_name=model_name)


def build_vector_index_from_env(embedding_dimension: int) -> VectorIndex:
    """根据环境变量创建向量索引。"""

    backend = os.getenv("AGENTFLOW_VECTOR_BACKEND", "memory").lower()
    if backend != "milvus":
        return InMemoryVectorIndex()

    return MilvusVectorIndex(
        host=os.getenv("MILVUS_HOST", "127.0.0.1"),
        port=os.getenv("MILVUS_PORT", "19530"),
        collection_name=os.getenv("MILVUS_COLLECTION", "agentflow_knowledge_chunks"),
        dimension=embedding_dimension,
    )
