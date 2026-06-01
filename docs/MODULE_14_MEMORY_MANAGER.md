# 模块 14：Memory Manager MVP

## 1. 模块目标

模块 14 实现 Agent 长期记忆的最小闭环：

- 长期记忆写入。
- 按 org/agent 隔离召回。
- Memory API。
- Context Engine 注入召回记忆摘要。

## 2. 当前实现范围

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/memory` | 写入 Agent 记忆 |
| POST | `/memory/recall` | 召回 Agent 记忆 |

## 3. 记忆类型

```text
fact
preference
task
decision
artifact
```

## 4. 隔离规则

- Memory 必须绑定 `org_id` 和 `agent_id`。
- 创建 Memory 需要 `agent:create` 权限。
- 召回 Memory 需要 `organization:read` 权限。
- 跨组织用户无法读取 Agent 记忆。

## 5. Context 集成

`/context/sessions/{session_id}/assemble` 当前会按 `current_input` 召回最多 5 条记忆，并注入：

```text
memories
```

每条记忆只注入摘要、类型和置信度，不直接注入完整敏感内容。

## 6. 当前限制

MVP 使用关键词召回和内存存储。后续会替换为：

- PostgreSQL 持久化。
- pgvector embedding 检索。
- 记忆去重。
- 敏感信息策略。
- Memory Agent 后台整理。

## 7. 测试

测试文件：

```text
apps/api/tests/test_memory_store.py
apps/api/tests/test_context_api.py
```

## 8. 下一步

模块 15：RAG MVP。

计划新增：

- Knowledge Base。
- Document。
- Chunk。
- 简单关键词检索 fallback。
- 后续替换 pgvector。

