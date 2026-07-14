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

## Gateway usage metering and Insights

The Gateway persists one immutable, organization-scoped usage event for a real
provider attempt. The Insights page and the read-only `/metering` API are
metering surfaces; they do not debit credits, create invoices, enforce token
budgets, or represent a provider invoice.

### Meaning of usage fields

| Field / label | Meaning |
| --- | --- |
| `provider_final` | The provider returned token usage. These token values are reported usage. |
| `unavailable` / `unknown` | The provider did not return the field. It is stored and shown as `NULL`/unknown, never as zero and never estimated from prompt or streamed character counts. |
| `estimated_*_cost` | Optional price-card calculation when configured. It is an estimate only, not a supplier charge, invoice, credit balance, or billing ledger. |
| `cache_read_input_tokens` | Provider-reported cached input tokens. A missing value means cache usage is unknown, not a cache miss. |
| `prefix_cache_status=eligible` | The request used the platform's stable-prefix-friendly shape. It is an optimization eligibility signal, not proof that the provider cache was read. |

Provider prompt-cache data, platform Redis/result-cache data, and stable-prefix
eligibility are intentionally separate. The current usage events record
provider cache fields and prefix eligibility. Platform cache hit rate is not
derived from these events and is shown as unavailable until independently
collected. For any cache-rate calculation, disclose the denominator: only
calls where the provider actually reported cache usage are covered; calls with
unknown or unsupported cache reporting must not be treated as misses.

### Data quality and streaming limits

The Gateway requests final usage from compatible streaming providers when they
support it. A completed stream without a final usage payload remains an
`unavailable` usage event. Text delivery remains usable, but no character-based
token estimate is added. Failed, rate-limited, cancelled, and missing-provider
attempts also create a terminal event whose usage may be unknown.

Usage events contain attribution and diagnostics only. They must not contain a
prompt, completion text, API key, authorization header, or a reversible plain
prefix hash. Events are idempotent per organization and gateway call ID and
are immutable after persistence.

### Access and operations

`GET /metering/usage/summary`, `GET /metering/usage/by-prefix`, and
`GET /metering/usage/events` require an authenticated identity scoped to the
organization and the read-only `ORGANIZATION_BILLING` permission. The server
derives organization and actor attribution; clients cannot supply them in a
Gateway generation body. Event responses are an explicit safe field allow-list
and do not expose prompt previews or provider credentials.

Deploy the Alembic revision `20260714_0002` before enabling Insights. It adds
`llm_usage_events`, `model_prices`, indexes, and a MySQL update-rejection
trigger for immutable usage facts. Validate the migration against the target
MySQL version in staging, then deploy API and web changes together. Rolling
back application code should first disable writes or restore a compatible
version; do not drop metering tables merely to roll back the UI. The Alembic
downgrade removes both tables and therefore intentionally discards metering
history; take and verify a database backup before using it.

