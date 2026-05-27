# 模块 17：RAG + Tool 节点真实执行

## 目标

本模块把 Workflow 画布中的 `RAG` 与 `Tool` 节点从占位输出升级为可运行能力。用户可以在前端选择知识库和已授权 MCP Tool，后端在 LangGraph DAG 执行时完成知识库检索、MCP 授权校验、工具调用计划生成和结果缓存。

## 后端结构

```text
packages/workflow/executor.py
apps/api/app/services/workflow_run_store.py
apps/api/app/services/knowledge_store.py
apps/api/app/services/mcp_store.py
apps/api/app/services/result_cache.py
apps/api/tests/test_workflow_run_store.py
```

`WorkflowExecutor` 只负责 DAG 编排，不直接依赖 FastAPI、知识库或 MCP。`WorkflowRunStore` 在创建执行器时注入 `rag_search` 和 `tool_call`，把用户、组织、Agent 上下文传入节点执行函数。

## RAG 节点数据流

1. 前端 DSL 写入 `kb_id`、`query_template`、`limit`。
2. 后端根据 `workflow_input` 和上游输出渲染 query。
3. `WorkflowRunStore` 使用 `knowledge_store.search` 检索 Chunk。
4. 节点输出包含 `kb_id`、`query`、`chunks`、`total_estimated_tokens`、`cache_hit`、`cache_key`。
5. 无命中时返回空 `chunks`，节点仍视为成功。

## Tool 节点安全边界

1. 前端 DSL 写入 `tool_id`、`tool_name`、`arguments`、`risk_level`。
2. 后端调用 `mcp_store.assert_agent_can_call_tool` 校验 Agent 是否被授权使用该 Tool。
3. MVP 阶段不请求外部 MCP Server，不产生副作用，只输出调用计划。
4. 高风险工具输出 `requires_approval: true` 和 `status: "requires_approval"`。
5. 未授权工具会让当前 Workflow Run 失败，并在 NodeRun 中记录错误。

## 缓存 Key

RAG 缓存：

```json
{
  "org_id": "...",
  "kb_id": "...",
  "query": "...",
  "limit": 5
}
```

Tool 缓存：

```json
{
  "org_id": "...",
  "agent_id": "...",
  "tool_id": "...",
  "arguments": {}
}
```

缓存类型分别为 `rag` 和 `tool`。节点输出会附加 `cache_hit` 与 `cache_key`，前端 Runs 页面可直接查看命中状态。

## 前端结构

`apps/web/features/workflows/WorkflowEditor.tsx` 新增：

- 默认完整链路画布：`Start -> RAG -> LLM -> Tool -> End`
- RAG 配置：知识库选择、Query 模板、Limit
- Tool 配置：已授权 MCP Tool 选择、Arguments JSON
- Runs 详情：节点输出、错误信息、缓存命中信息

## 测试覆盖

后端单元测试覆盖：

- RAG 有命中并输出 chunks。
- RAG 无命中但节点成功。
- Tool 已授权时输出调用计划。
- Tool 未授权时 Workflow Run 失败。
- 相同 RAG/Tool 输入第二次运行命中缓存。

## 当前限制

- RAG 仍使用关键词检索，未接入 embedding 或 pgvector。
- Tool 节点不会执行外部 MCP 副作用，只做授权校验和调用计划。
- 前端节点配置当前是工作台级配置，后续可演进为“选中节点侧边栏配置”。
