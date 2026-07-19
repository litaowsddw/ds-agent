# 实时用量进度与 Skill 创建意图设计

**日期：** 2026-07-19
**状态：** 已获方案批准，待规格审阅
**范围：** 自主对话、显式 Skill 创建与 Workflow 聊天模式

## 目标

1. 在模型生成期间持续显示本轮 Token 用量的本地估算；模型结束后以 Provider 返回的最终 usage 校准。
2. 让 Workflow 中的每个 LLM 节点也能向聊天 SSE 传递用量进度，并在界面中汇总。
3. 只有用户明确要求“创建/生成/新建 Skill（技能）”时，才允许创建 Skill、写入文件并持久化授权。

## 非目标

- 不把本地估算伪装成 Provider 的实际计费数据。
- 不实现费用结算、配额扣减或后台 Worker 的实时进度推送。
- 不将所有 Gateway 调用方重构为一套全局破坏性事件协议。
- 不在本轮修改现有已创建 Skill 的检索与使用逻辑。

## 用量语义与 SSE 契约

现有事件名称保持兼容，并为所有用量事件补充统一上下文：

- usage_scope：chat、skill_create 或 workflow。
- usage_key：本次模型调用的稳定标识；Workflow 使用 workflow_run_id:node_id。
- workflow_node_id：仅 Workflow LLM 节点携带。
- usage_phase：preflight、estimated、provider_final 或 unavailable。

事件语义如下：

| 事件 | 时机 | 数据可信度 |
| --- | --- | --- |
| context_preflight | 请求模型前 | 输入 Token 的本地 tokenizer/字符估算 |
| context_progress | 每个文本 chunk 后 | 本次调用输出与本轮累计用量的本地估算 |
| context_usage | Provider 调用结束后 | Provider 最终 usage；Provider 未提供时明确标记 unavailable |

前端按 usage_key 保存调用状态并汇总为“本轮累计”。只要仍存在估算或未知调用，界面显示“实时估算”或“部分已校准”；所有调用均有 Provider 最终 usage 时才显示“Provider 已校准”。Provider 的隐藏 token 或缓存字段可使最终值与估算值不同，这是正常校准而非错误。

## 后端设计

### 自主对话

保留当前 LLMGateway.stream_generate 的逐文本 chunk 调用。聊天路由将提取“请求前计数、chunk 后估算、结束后最终 usage”封装为共享的流式用量辅助逻辑，确保三个路径的字段和顺序一致。

### 显式 Skill 创建

Skill 创建分支不再使用一次性 LLMCallerAdapter.call。它将以流式方式消费生成 SKILL.md 的文本：

1. 为 Skill Creator 的实际 system/user prompt 发送 preflight。
2. 每个 chunk 更新 context_progress，但不把未校验的 SKILL.md 原文作为聊天回答输出。
3. 完成后发送最终 context_usage，验证 Markdown，再依序写文件、创建数据库记录和授权。
4. 仅在所有写入成功后发送 skill_created。

这样保留现有“创建完成后才展示结果”的交互，同时让用量在生成期间持续更新。

### Workflow 聊天模式

Workflow 执行器继续负责 DAG 编排和节点结果持久化；不在其通用同步接口中引入聊天协议。聊天专用的执行服务新增可选用量进度回调：

1. 聊天路由以异步队列启动并消费 Workflow 执行任务，队列中的事件立即转换为 SSE。
2. Workflow 执行服务为聊天调用注入回调；普通 API/Worker 调用不传回调，维持原有行为。
3. LLM 节点新增流式调用辅助方法：构建与现有节点相同的请求，发送节点 preflight，逐 chunk 累积文本与估算，再在结束时报告 Provider 最终 usage。
4. 节点完成后仍向 WorkflowExecutor 返回完整字典结果，并沿用现有 Run/NodeRun 持久化逻辑。
5. 客户端断开或节点失败时，取消执行任务、关闭上游流并发送可辨识的失败或取消状态；不得把部分估算写成最终 Provider usage。

该设计让聊天页在 Workflow 运行时显示活动节点和本轮累计 Token，同时不改变后台异步 Workflow 的执行语义。

## Skill 创建安全阀

detect_skill_creation_request 改为严格、默认拒绝的解析规则：

- 中文必须同时含有创建动作（创建/生成/新建）与对象词“Skill/技能”，且动作指向该对象。
- 英文必须匹配明确的命令式结构，例如 create a skill 或 generate skill。
- “如何/怎么/能否/是否/解释/介绍创建 Skill”等咨询、说明或否定语句均不是创建请求。
- 任何未通过严格解析的输入都进入既有的普通聊天与 Skill 检索路径。

路由只接收结构化的明确创建意图；写文件、创建数据库 Skill、设置 Agent 授权和发出 skill_created 前再检查该意图。前端只展示服务端已经完成的事件，不承担创建决策。

## 错误处理

- Provider 不返回 usage：保留最后一个估算值，并标为 unavailable，不替换为零。
- 单个 Workflow 节点失败：保留已完成节点的最终值和当前节点最后估算；运行按现有失败语义结束。
- 取消：显示已观察到的估算，但不生成 Provider 最终值。
- Skill Markdown 校验或持久化失败：不发送 skill_created；返回错误事件且不把失败半成品当作有效 Skill。

## 验证策略

先写失败测试，再实现：

1. Skill 意图正例、普通创建语句负例与咨询语句负例；负例必须断言无文件写入、无 Skill DB 创建、无授权和无 skill_created。
2. 自主对话与显式 Skill 创建的 SSE 顺序：preflight → 多个递增的 progress → final usage。
3. 含 LLM 节点的 Workflow 聊天测试：在 run_finished 前收到节点级 progress，前端累计值递增，且节点完成后持久化结果不变。
4. Provider usage 缺失、Provider 最终值与估算不一致、取消及节点失败的回归测试。
5. 前端 store 与 Composer 测试：实时估算、部分校准、全部校准和 Workflow 活动节点状态均正确渲染。

## 验收标准

- 普通“创建/生成/新建某物”不再创建 Skill；明确创建 Skill 的请求仍成功。
- 三条聊天路径均能在模型响应完成前显示递增的本地估算。
- Workflow 的最终聊天结果、Run 状态和 NodeRun 持久化与改动前保持兼容。
- 页面清楚区分实时估算、Provider 已校准和 Provider 未提供 usage 三种状态。
