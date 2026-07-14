# Gateway 可信用量计量设计

## 目标

为每一次实际发往模型供应商的请求建立可审计、可跨进程查询的用量事实记录，并提供组织内按 API、Provider、模型、Agent、Workflow、运行记录和时间聚合的 Token 与缓存命中洞察。

首期交付的是可信的 **metering**，不是对客户扣费的 billing 系统。金额仅在存在版本化费率时作为 `estimated_cost` 展示；不实现额度、扣费、发票、退款或跨期结算。

## 已确认的产品边界

- 用户先创建 Agent；未设置 Workflow 时可以直接自主对话。
- 已发布的默认 Workflow 是该 Agent 的默认受控执行策略；用户可以对当前会话或消息临时选择自主对话。
- 用量明细必须能关联 Agent、Chat 会话、Workflow、Run 和 LLM 节点，但同一次 Provider 调用只能计量一次。
- 只有供应商明确返回的 usage 才是实际 Token；本地字符估算、最大输出 Token 和 prefix 指纹都不能作为实际消耗或账单依据。
- Provider 报告的 prompt cache token 与平台 Redis/结果缓存是两类指标，必须分开存储、聚合和展示。

## 当前问题

`LLMGateway` 只把 `LLMCallLog` 保存在进程内列表；重启、多副本和 Worker 调用都会丢失或漏记。流式调用使用输出字符数估算 Token，且缓存未返回时被错误视为全部未命中。Gateway、Chat 和部分运行路由仍信任请求体中的组织和用户 ID，无法作为租户计量边界。

## 方案

### 1. 不可变 usage 事实层

新增 `llm_usage_events`。一行对应一次真实发往 Provider 的请求尝试，而不是一次页面点击或一次 Workflow Run。

每次 Gateway 调用开始生成 `logical_request_id` 与 `gateway_call_id`：

- `logical_request_id` 连接上层的一次逻辑请求。
- 每个 HTTP 尝试有独立 `gateway_call_id` 与 `attempt_no`。
- 重试创建新事件，并以 `retry_of_event_id` 关联；不能覆盖前一次可能已消耗的请求。
- `(org_id, gateway_call_id)` 唯一，事件写入使用幂等 upsert，防止 Worker/重试重复记账。

事实记录的最小字段：

| 类别 | 字段 |
| --- | --- |
| 标识 | `event_id`, `gateway_call_id`, `logical_request_id`, `attempt_no`, `retry_of_event_id` |
| 归因 | `org_id`, `actor_user_id`, `agent_id`, `session_id`, `workflow_id`, `workflow_version_id`, `workflow_run_id`, `workflow_node_id`, `source`, `api_name` |
| Provider | `provider_config_id`, `provider_key`, `model`, `provider_request_id`, `is_stream` |
| 生命周期 | `dispatch_status`, `usage_status`, `delivery_status`, `started_at`, `completed_at`, `latency_ms` |
| 实际用量 | `input_tokens`, `output_tokens`, `reasoning_tokens`, `total_tokens`, `total_tokens_kind` |
| Provider 缓存 | `cache_read_input_tokens`, `cache_write_input_tokens`, `cache_miss_input_tokens`, `cache_usage_status` |
| 前缀诊断 | `prefix_fingerprint`, `prefix_schema_version`, `prefix_eligible_input_tokens_estimate` |
| 费用预留 | `price_version_id`, `input_cost_microusd`, `output_cost_microusd`, `cache_read_cost_microusd`, `total_cost_microusd`, `currency` |
| 错误审计 | `error_class`, `provider_status_code`, `error_code`, `error_safe_message` |

敏感内容不进入该表：不得保存 Prompt、Completion、API Key、Authorization 或未脱敏的 Provider 响应。前缀使用组织级、可轮换 key 的 HMAC 指纹，不公开当前 SHA-256 值。

### 2. Token 与缓存语义

所有真实 Token 字段允许 `NULL`。`0` 只表示 Provider 明确报告了零。

- 非流式成功：从 Provider 最终 `usage` 映射 `input_tokens`、`output_tokens`、`total_tokens`。如总量未提供但输入和输出都已知，可派生总量并标记 `derived`。
- Provider 缓存命中：仅 Provider 明确报告的 cached/read token 计入 `cache_read_input_tokens`。缓存字段未提供时 `cache_usage_status=unknown`，不得默认未命中。
- `cache_miss_input_tokens` 仅在 Provider 明确报告，或输入和缓存读取均为实际已知时严格派生；否则为 `NULL`。
- 流式调用：Provider 支持最终 usage chunk 时，收到该 chunk 后完成事件；未提供时调用可成功但 `usage_status=unavailable`。不得再使用字符数除以四写入实际用量。
- 客户端中断：记录 `delivery_status=client_cancelled`。已收到的 Provider 最终 usage 仍按实际保存；否则为 unknown。
- 本地限流或鉴权在请求尚未发送前拒绝时，事件为 `not_dispatched`，可明确计为 Provider Token 0。超时、网络中断或 Provider 错误未带 usage 时为 unknown，不能计 0。

稳定前缀只表示“具备 prefix-cache 优化资格”。报表必须分开显示：

- `prefix_eligible_input_tokens_estimate`：稳定前缀覆盖诊断。
- `cache_read_input_tokens`：Provider 实际命中的 Token。

相同前缀且 Provider 报告零命中仍是未命中；不同前缀也不能推翻 Provider 的真实命中报告。

### 3. 网关集成与归因

新增独立 metering 域，而不是把财务语义放进 Gateway 路由：

```text
Gateway 请求
  -> Authenticated execution context
  -> LLMGateway / Provider adapter
  -> UsageRecorder (开始、完成或失败)
  -> llm_usage_events
  -> metering aggregation API
  -> Insights / Agent / Run 摘要
```

`LLMGateway` 接受异步 `UsageRecorder`，在成功、失败和流式终态的唯一出口写事件。HTTP Gateway、Chat 自主模式、Chat Workflow 模式、画布 Workflow、Celery Worker 和 Runtime Adapter 都注入同一 recorder；禁止从进程内 `call_logs` 事后搬运。

所有归因字段由认证上下文与服务端运行上下文产生：

- HTTP Gateway 从 JWT 和组织成员关系获得用户与组织。
- Chat 从当前 Agent、Session 和认证用户获得归因。
- Workflow 节点附带 Workflow/版本/Run/节点及当前 Agent。
- Worker 从已持久化 Run 的组织与创建者恢复上下文。

请求体的 `org_id`、`actor_user_id` 不能成为授权或写账依据。此改动同时收紧 Gateway、Chat 与 Workflow Run 的认证边界。

### 4. 费用预留与后续账单

首期可以存储版本化 `model_price_cards`，以 Provider + 精确模型 + 生效时间定义 input、output、cache-read 与 cache-write 的微美元单价。若命中费率，事件写入对应版本与 `estimated_cost`；如果没有价格或 usage unknown，成本为 `NULL` 并明确标记 `unpriced` 或 `unmetered`。

不创建信用额度、冻结、扣费、退款、发票或账本分录。正式 billing 必须以后续 Provider 对账、费率治理和独立的不可变 ledger 为前提。

### 5. 组织级 API 与权限

新增受保护的计量接口：

- `GET /metering/usage/summary`：按小时/日、API、Provider、模型、Agent、Workflow、来源和状态聚合。
- `GET /metering/usage/by-prefix`：仅聚合稳定前缀资格、Provider cache-read Token 和数据覆盖率；不返回 Prompt 或可逆前缀。
- `GET /metering/usage/events`：组织管理员分页查看脱敏原始事实。
- `PUT /metering/model-prices`：组织 owner 管理费率版本；该端点属于第二个小切片，可在首期仅预留 schema。

所有接口都使用 JWT 与组织成员/RBAC，后端强制追加 `org_id=authenticated_org_id` 过滤。普通成员只能查询自己有权限的 Agent/Run 摘要；Agent 管理者可看受管 Agent；组织管理员可看组织聚合；Prompt、API Key 和跨组织事件永不可见。

缓存比率需返回 coverage：

```text
actual_cache_read_rate =
  sum(cache_read_input_tokens) /
  sum(input_tokens for rows where cache_usage_status is known)
```

未知缓存数据不能进入分母，更不能被当作未命中。

### 6. 用户体验

新增 `/insights` 作为“运行与观测”域的组织级入口：管理员可按时间、API、Provider/模型、Agent、Workflow、来源、状态和数据质量筛选。默认显示最近七天的调用数、输入/输出/总 Token、成功率、p50/p95 延迟、Provider cache-read Token、数据覆盖率和可选估算费用。

Agent 页面仅显示当前 Agent 的近七天轻量摘要并链接至带 `agent_id` 筛选的 Insights；Chat 和 Runs 只显示本次运行的折叠摘要。平台 Redis/结果缓存在 Insights 的独立区块显示，不能与 Provider prompt cache 或成本节省混为一谈。

用户界面必须清楚区分：

- `真实`：Provider 返回 usage。
- `估算`：仅诊断用途，以 `~` 标识，不能汇入实际成本。
- `未知`：显示 `—` 和原因，不能显示 0。
- `不支持`：Provider 未上报缓存字段，不表示未命中。

### 7. 与平台后续优化的关系

本规格为后续两个独立切片建立运行事实：

1. **工具执行体系**：内置常用工具、MCP 真实调用、Agent 精确授权、审批与审计。工具事件写入 Run/Trace，但不重复生成 LLM usage 事件。
2. **Agent-first 体验闭环**：默认 Workflow 成为 Chat 的默认受控策略；Workflow 发布/发送前进行可执行性预检；Chat 将用户答案、技术详情与 Run 深链分开呈现。

## 非目标

- 不对历史内存日志回填。
- 不把任何本地 Token 估算当作实际 Token 或账单。
- 不引入外部支付、订阅、发票或信用额度。
- 不在首期新增高风险工具、任意 HTTP、Shell 或代码执行。
- 不改变默认 Workflow 只能属于当前 Agent 且必须已发布的既有约束。

## 验收标准

- 非流式完整 usage、缓存字段缺失、流式最终 usage、流式无 usage、客户端中断、429、超时和重试都有确定的事件状态；未知字段始终为 `NULL` 而非零或估算。
- Provider 明确报告的 cache-read Token 才进入缓存命中聚合；稳定前缀资格不冒充实际命中。
- HTTP Gateway、Chat 自主模式、Chat Workflow、画布 Run 和 Worker 调用均通过同一 recorder；每次实际 Provider 请求只产生一个 usage 事件并包含正确的 Agent/Session/Run/节点归因。
- 无 JWT 为 401；跨组织查询或伪造请求体的用户/组织 ID 为 403；任何事件、报表或日志都不包含 Prompt、Completion、密钥或 Authorization。
- 数据库迁移可在 MySQL 上 upgrade/downgrade/upgrade；事实表手工求和与 API 聚合一致，重启后数据仍存在。
- 组织管理员可筛选 API、模型、Agent、Workflow、来源、时间和数据质量；普通成员无法通过页面或 API 读取其他 Agent 或组织级明细。
- 未配置费率时 Token 仍可用、费用为 unavailable；费率变更不得重算既有事件的估算费用。

