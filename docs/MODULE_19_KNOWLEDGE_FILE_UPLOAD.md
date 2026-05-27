# 模块 19：知识库文件上传与解析

## 目标

本模块让知识库从“只能粘贴纯文本”升级为可直接上传文件。上传后后端会解析文件文本，复用模块 18 的切片、embedding 和 Milvus/内存向量索引链路。

## 支持格式

```text
.txt
.md / .markdown
.csv
.json
.log
.pdf
.docx
```

## 后端流程

1. 前端使用 `multipart/form-data` 调用 `POST /knowledge/{kb_id}/documents/upload`。
2. `DocumentParser` 根据文件后缀解析文本。
3. `KnowledgeStore.upload_document` 创建 Document。
4. 文档内容按 `chunk_size` 和 `chunk_overlap` 切片。
5. 切片生成 embedding 并写入 Milvus。
6. 检索结果返回 `vector_indexed`、`embedding_model` 和 `similarity_score`。

## 关键文件

```text
apps/api/app/services/document_parser.py
apps/api/app/routes/knowledge.py
apps/api/requirements.txt
apps/api/tests/test_knowledge_api.py
apps/web/features/workflows/WorkflowEditor.tsx
```

## 前端体验

Knowledge 页面现在支持：

- 选择知识库
- 选择本地文件上传
- 没有选择文件时继续支持手动文本上传
- 查看上传文档状态
- 检索时查看向量索引状态、embedding 模型和相似度分数

## 当前限制

- PDF 解析依赖 PDF 内部存在可抽取文本，扫描件 OCR 尚未接入。
- 文件大小、异步索引队列和失败重试还未做生产级控制；下一阶段应把大文件索引迁移到 Celery 任务。
