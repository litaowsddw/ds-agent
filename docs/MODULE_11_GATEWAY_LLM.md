# 模块 11：Gateway + LLM Provider

## 1. 模块目标

模块 11 建立 LLM 调用的统一出口：

- LLM Provider 协议。
- Mock LLM Provider。
- OpenAI-compatible Provider 适配器骨架。
- LLM Gateway 调用日志。
- Provider 错误标准化。
- Workflow LLM 节点通过 Gateway 调用。

## 2. 当前实现范围

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/gateway/llm/generate` | 通过 Gateway 调用 LLM |
| GET | `/gateway/llm/logs` | 查看 LLM 调用日志 |

核心代码：

```text
apps/api/app/gateway/llm.py
packages/workflow/executor.py
apps/api/app/services/workflow_run_store.py
```

## 3. Gateway 调用链

```text
WorkflowExecutor
  -> llm_gateway callable
  -> LLMGateway.generate_from_workflow_node
  -> LLMGateway.generate
  -> LLMProvider.generate
  -> LLMCallLog
```

## 4. Provider

当前 Provider：

| Provider | 说明 |
| --- | --- |
| `mock` | 本地确定性响应，不访问网络 |
| `OpenAICompatibleProvider` | 接口骨架，后续接 HTTP Client 和密钥管理 |

## 5. 调用日志

`LLMCallLog` 当前记录：

- `call_id`
- `provider`
- `model`
- `prompt_preview`
- `status`
- `usage`
- `error_message`
- `metadata`

后续会扩展：

- `org_id`
- `agent_id`
- `workflow_run_id`
- `node_run_id`
- `prefix_hash`
- `cost`

## 6. 测试

测试文件：

```text
apps/api/tests/test_llm_gateway.py
apps/api/tests/test_workflow_run_store.py
```

覆盖场景：

- Gateway 成功调用并记录日志。
- 未注册 Provider 会标准化错误。
- Workflow LLM 节点通过 Gateway 生成输出。

## 7. 下一步

模块 12：Prompt Context Compiler + Reasonix prefix-cache 友好设计增强。

计划新增：

- Workflow LLM 节点接入稳定 Prompt 编译。
- prefix hash 记录到 LLM 日志。
- immutable prefix / append-only log / current turn 分层。
- cache hit token 指标字段贯通。

