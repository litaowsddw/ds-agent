# 模块 12：Prompt Context Compiler + Reasonix Prefix-cache 友好设计

## 1. 模块目标

模块 12 将 Reasonix 风格 Prompt 编译接入 LLM Gateway：

- LLM 节点 Prompt 分为三段。
- 稳定前缀生成 `prefix_hash`。
- LLM 调用日志记录 `prefix_hash`。
- 当前动态输入后置，减少对 prefix-cache 的破坏。

## 2. Prompt 分层

```text
IMMUTABLE_PREFIX
  system_prompt
  model
  tool_schemas
  output_contract

APPEND_ONLY_LOG
  upstream node outputs

CURRENT_TURN
  node prompt
  workflow input
```

## 3. 当前实现

核心代码：

```text
packages/runtime/prompt_compiler.py
apps/api/app/gateway/llm.py
```

`LLMGateway.generate_from_workflow_node` 会：

1. 从 LLM 节点 config 构建 immutable prefix。
2. 从上游节点输出构建 append-only log。
3. 从当前 workflow input 和 node prompt 构建 current turn。
4. 调用 `PromptContextCompiler.compile`。
5. 将 `prefix_hash` 写入 LLM 响应和调用日志。

## 4. 验收规则

- 相同稳定前缀、不同 current turn，应生成相同 `prefix_hash`。
- LLM 日志必须包含 `prefix_hash`。
- Workflow Run 的 LLM 节点输出必须包含 `prefix_hash`。

## 5. 测试

测试文件：

```text
apps/api/tests/test_llm_gateway.py
apps/api/tests/test_workflow_run_store.py
packages/runtime/tests/test_prompt_compiler.py
```

## 6. 下一步

模块 13：全局限流与并发控制。

计划新增：

- Redis token bucket 抽象。
- 本地 fallback 限流器。
- provider/model/org/agent 多维限流 key。
- Gateway 调用前限流检查。

