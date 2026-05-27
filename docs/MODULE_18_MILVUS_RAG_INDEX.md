# 模块 18：Milvus RAG 向量索引

## 目标

本模块把知识库上传链路升级为“上传文档 -> 切片 -> 生成 embedding -> 写入向量数据库 -> 向量检索”。生产环境采用 Milvus Standalone，测试和本地无 Milvus 服务时保留内存向量索引回退。

## 技术栈

- 向量数据库：Milvus Standalone
- Python SDK：pymilvus
- Embedding Provider：当前为 `local-hash-embedding-v1` 确定性本地 embedding
- 检索方式：归一化向量内积相似度，Milvus HNSW 索引

## 关键文件

```text
apps/api/app/services/knowledge_vector_index.py
apps/api/app/services/knowledge_store.py
apps/api/app/domain/knowledge.py
apps/api/app/schemas/knowledge.py
apps/api/app/routes/knowledge.py
apps/api/tests/test_knowledge_store.py
apps/api/tests/test_knowledge_api.py
docker-compose.yml
.env.example
```

## 上传与索引流程

1. 前端或 API 调用 `POST /knowledge/{kb_id}/documents` 上传文档。
2. `KnowledgeStore` 校验用户对知识库所属组织的写权限。
3. `_split_text` 按 `chunk_size` 和 `chunk_overlap` 生成 Chunk。
4. `EmbeddingProvider.embed_texts` 批量生成 embedding。
5. Chunk 元数据保存在本地状态 Store。
6. `VectorIndex.upsert_chunks` 将向量写入 Milvus 或内存索引。
7. 文档状态变为 `indexed`。

## Milvus Collection

默认 collection：`agentflow_knowledge_chunks`

字段：

```text
chunk_id: VARCHAR primary key
org_id: VARCHAR
kb_id: VARCHAR
document_id: VARCHAR
sequence: INT64
estimated_tokens: INT64
content: VARCHAR
embedding: FLOAT_VECTOR(256)
```

索引：

```text
index_type: HNSW
metric_type: IP
params: M=16, efConstruction=128
```

因为 embedding 已归一化，内积可作为余弦相似度使用。

## 检索流程

1. `KnowledgeStore.search` 对 query 生成 embedding。
2. 向量索引按 `org_id` 和 `kb_id` 过滤，避免跨租户命中。
3. 返回命中的 Chunk，并附加：
   - `embedding_model`
   - `vector_indexed`
   - `similarity_score`
4. 如果向量索引无命中，则回退到关键词检索。

## 环境变量

```env
AGENTFLOW_VECTOR_BACKEND=milvus
AGENTFLOW_EMBEDDING_MODEL=local-hash-embedding-v1
AGENTFLOW_EMBEDDING_DIMENSION=256
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_COLLECTION=agentflow_knowledge_chunks
```

本地不启动 Milvus 时可设置：

```env
AGENTFLOW_VECTOR_BACKEND=memory
```

## 当前限制

- 当前 embedding 是本地确定性 hash embedding，只用于 MVP 链路打通；后续应替换为真实 embedding 模型。
- 文档解析已在模块 19 支持 txt/md/pdf/docx 等文件；扫描件 OCR 尚未接入。
- Milvus 当前使用 Standalone 部署，生产环境后续可演进为 Milvus Cluster。
