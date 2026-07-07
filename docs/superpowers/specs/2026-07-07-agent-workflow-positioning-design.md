# Agent 与 Workflow 产品定位优化设计

日期：2026-07-07

## 1. 背景

当前 ds-agent 同时呈现了 Agent 搭建、智能体对话、可视化 Workflow 搭建、Runtime 管理、Knowledge、Skill Evolver 等能力。代码层面已经有正确的基础关系：Workflow 数据模型绑定 `agent_id`，Workflow Run 也记录 `agent_id`。但产品体验和运行链路还没有把这个关系表达清楚：

- `/agents` 主要是 Agent 参数和 Workspace 文本编辑，没有成为核心工作台。
- `/workflows` 更像独立 Workflow 产品，而不是 Agent 的可选执行策略。
- `/chat` 走 Agent Runtime，`/workflow-runs` 走 WorkflowExecutor，两条路径没有在用户体验上统一。
- README 和开发计划把 Agent Runtime 与 Workflow Layer 写成并列主线，容易让用户误解核心功能。

本设计将项目主线收敛为：ds-agent 是 Agent 构建与运行平台，Workflow 是绑定到 Agent 的可选流程约束能力。

## 2. 产品原则

### 2.1 Agent 是主角

用户的第一目标是创建、配置、运行和持续优化 Agent。Agent 可以在没有 Workflow 的情况下独立处理任务，适合开放式、探索式、对话式和需要自主判断的任务。

### 2.2 Workflow 是可选约束层

Workflow 不再被表达为独立主产品，而是某个 Agent 的流程策略。它用于规范固定链路、稳定输入输出、过程审计和可复现执行。没有 Workflow 的 Agent 仍然是完整可用的 Agent。

### 2.3 用户可明确选择运行模式

第一阶段不做自动路由。用户在 Chat 或运行入口中明确选择：

- 自主模式：直接由 Agent Runtime 处理。
- 流程模式：选择一个已发布 Workflow，由该 Workflow 约束执行链路。

Agent 可以配置默认 Workflow，但默认 Workflow 为空时，Agent 仍默认自主运行。

## 3. 第一阶段目标

1. 重塑信息架构：让 `/agents` 成为 Agent 工作台，Workflow 成为 Agent 的能力模块。
2. 明确运行模式：Chat 支持自主模式与流程模式。
3. 打通最小后端链路：Chat 请求可选择 Workflow 执行，并把结果保存到 Agent Session。
4. 保持现有 Workflow 编辑器能力：继续支持创建、保存、发布、运行，但按当前 Agent 过滤。
5. 更新文档和项目定位：避免“Workflow 平台”和“Agent 平台”抢主线。

## 4. 非目标

第一阶段不做以下内容：

- 不实现 Agent 自动判断是否调用 Workflow。
- 不扩展所有 schema-only Workflow 节点的真实后端执行。
- 不重做完整权限模型。
- 不重构所有 Runtime、Skill、MCP、Memory 模块。
- 不引入新的前端 UI 框架或大型状态管理方案。

## 5. 用户体验设计

### 5.1 导航

导航保留现有页面，但调整心智模型：

- `Agents`：主工作台，创建、选择和配置 Agent。
- `Chat`：运行 Agent，可选择自主模式或流程模式。
- `Workflows`：当前 Agent 的流程策略编辑器。
- `Runtime`、`Knowledge`、`Runs`：作为 Agent 能力与运行观测页面保留。

后续可考虑将 `Workflows` 入口视觉上降级为 Agent 工作台的子入口，但第一阶段保留路由，减少改动风险。

### 5.2 Agent 工作台

`/agents` 从单纯管理页升级为 Agent 工作台：

- 左侧：Agent 列表和创建入口。
- 主区：Agent 基础配置，包括名称、描述、模型供应商、模型、系统提示词、temperature、max tokens。
- 能力概览：显示当前 Agent 已绑定的 Knowledge、Skills、MCP Tools、Sessions、Workflows。
- Workflow 策略：显示该 Agent 的 Workflow 列表、发布状态、默认 Workflow 选择。
- Workspace：继续支持 AGENTS.md 等文件编辑，后续可扩展 SOUL、TOOLS、MEMORY。

### 5.3 Workflow 编辑器

`/workflows` 必须始终围绕当前选中的 Agent 工作：

- 未选择 Agent 时，提示先选择或创建 Agent。
- Workflow 列表只显示当前 Agent 下的 Workflow。
- 创建 Workflow 时自动绑定当前 Agent。
- 页面标题和空态文案表达为“Agent workflow strategy”，而不是独立 Workflow 平台。

### 5.4 Chat 运行模式

Chat 页面增加执行模式控件：

- 自主模式：默认值。请求不传 Workflow，调用现有 Agent 对话链路。
- 流程模式：用户选择一个已发布 Workflow。请求传 `execution_mode = "workflow"` 和 `workflow_id`。
- 默认流程：如果 Agent 配置了默认 Workflow，Chat 可提供“使用默认流程”的快捷选项，但不强制使用。

当流程模式执行完成后，Chat 中展示 Workflow 输出，并在 Session 消息中保存用户输入和最终结果。Run Trace 仍在 Runs 或 Workflow Run 页面查看。

## 6. 后端设计

### 6.1 Agent 模型扩展

Agent 增加可选默认 Workflow 引用：

```text
default_workflow_id: str | None
```

约束：

- 默认 Workflow 必须属于同一个 Agent。
- 默认 Workflow 应优先指向已发布版本，未发布 Workflow 不能作为稳定默认流程。
- 字段为空表示 Agent 默认自主运行。

如果短期不想修改数据库结构，可先使用 Agent 配置扩展字段或独立策略表。但推荐直接建字段，因为语义清晰、查询简单。

### 6.2 Chat API 扩展

`ChatRequest` 增加：

```text
execution_mode: "autonomous" | "workflow" = "autonomous"
workflow_id: str | None = None
```

行为：

- `execution_mode = "autonomous"`：沿用现有 Agent Runtime 或 streaming chat 链路。
- `execution_mode = "workflow"`：校验 Workflow 属于该 Agent 且有发布版本，然后执行 Workflow。
- `workflow_id` 为空但 Agent 有 `default_workflow_id` 时，可使用默认 Workflow。
- `workflow_id` 为空且没有默认 Workflow 时，返回 400，提示选择 Workflow 或改用自主模式。

### 6.3 Workflow 执行接入

流程模式应复用现有 WorkflowExecutor 和 Workflow Run 持久化，而不是复制执行逻辑：

1. 根据 `workflow_id` 读取 Workflow。
2. 校验 `workflow.agent_id == request.agent_id`。
3. 读取 `published_version_id` 与版本定义。
4. 创建 Workflow Run，`input_data` 来自用户消息。
5. 同步或异步执行现有 WorkflowExecutor。
6. 保存 Node Runs。
7. 将最终输出转成 Chat assistant message。

第一阶段以同步执行为主，避免 Chat 页面同时处理复杂任务排队。已有异步能力保留给 Workflow Runs 页面。

### 6.4 Session 记录

无论自主模式还是流程模式，都应保存到同一个 Agent Session：

- user message：原始用户输入。
- assistant message：自主回答或 Workflow 最终输出。
- metadata：建议记录 `execution_mode`、`workflow_id`、`workflow_run_id`。

这样用户在 Chat 中看到的是同一个 Agent 的连续使用历史，而不是两个割裂产品。

## 7. 前端设计

### 7.1 类型与 Store

前端 Agent 类型增加：

```ts
default_workflow_id?: string | null;
```

Workflow store 的刷新接口应支持 `agent_id` 过滤。当前 `refreshWorkflows(orgId, actorUserId)` 应扩展为可传当前 Agent：

```ts
refreshWorkflows(orgId, actorUserId, agentId?)
```

Chat store 请求增加执行模式和 Workflow ID。

### 7.2 Agents 页面

新增或调整以下区域：

- Agent 配置区：保留现有参数编辑。
- Agent 能力概览：使用现有 metrics，但补充 Workflows 数量。
- Workflow 策略区：列出当前 Agent 的 Workflows，支持选择默认 Workflow。
- 快捷入口：进入 Workflow 编辑器时保持当前 Agent 选中。

### 7.3 Workflows 页面

调整点：

- `refreshWorkflows` 使用 `selectedAgentId` 过滤。
- 顶部显示当前 Agent 名称。
- 创建、保存、发布、运行文案改成围绕 Agent 的流程策略。
- 未选择 Agent 时显示阻断空态。

### 7.4 Chat 页面

新增模式选择：

- segmented control：自主模式 / 流程模式。
- 流程模式下显示 Workflow selector，只列出当前 Agent 已发布 Workflow。
- 如果没有已发布 Workflow，提示可先去 Workflows 页面创建和发布，但不影响自主模式。

## 8. 数据流

### 8.1 自主模式

```text
User input
  -> Chat API
  -> Agent Runtime
  -> LLM Gateway / Skill / Memory
  -> Session messages
  -> Chat response
```

### 8.2 流程模式

```text
User input
  -> Chat API
  -> Workflow ownership and published-version check
  -> Workflow Run create
  -> WorkflowExecutor
  -> Node Runs persist
  -> Session messages with workflow metadata
  -> Chat response
```

## 9. 错误处理

- 没有选择 Agent：前端阻断，提示先选择 Agent。
- 自主模式下 Agent 未配置模型：沿用现有 400 错误，前端引导去 Agent 配置。
- 流程模式下没有 Workflow：前端提示使用自主模式或创建 Workflow。
- Workflow 未发布：不允许作为流程模式执行。
- Workflow 不属于 Agent：后端返回 403 或 400，避免跨 Agent 执行。
- Workflow 节点执行失败：Chat 显示失败摘要，Runs 页面显示节点级日志。

## 10. 测试策略

### 10.1 后端

- 创建 Agent 时默认 Workflow 为空。
- 设置默认 Workflow 时校验归属关系。
- Chat 自主模式不要求 Workflow。
- Chat 流程模式必须选择已发布 Workflow 或可使用默认 Workflow。
- 流程模式执行后写入 Session 消息和 Workflow Run。
- 跨 Agent Workflow 调用失败。

### 10.2 前端

- Agent 页面显示当前 Agent 的 Workflow 策略区。
- Workflows 页面按 selectedAgentId 过滤。
- Chat 默认自主模式。
- Chat 流程模式只展示已发布 Workflow。
- 无 Workflow 时自主模式仍可发送消息。

### 10.3 集成

- 创建 Agent -> 直接 Chat 成功。
- 创建 Agent -> 创建并发布 Workflow -> Chat 选择流程模式 -> 返回 Workflow 输出并保存会话。

## 11. 文档更新

需要同步更新：

- README：项目定位改为 Agent 构建与运行平台，Workflow 是 Agent 的可选流程策略。
- CURRENT_STATUS：说明新的产品主线。
- DEVELOPMENT_PLAN：调整总体架构描述，避免把 Workflow 描述为独立主产品。
- PROJECT_STRUCTURE：标注 Workflow 与 Agent 的归属关系。

## 12. 实施顺序建议

1. 文档定位更新。
2. 后端 schema/model/API 支持 `default_workflow_id` 和 Chat execution mode。
3. Workflow 查询按 Agent 过滤并补测试。
4. 前端 store 与类型更新。
5. Agents 页面增加 Workflow 策略区。
6. Workflows 页面按 Agent 收敛。
7. Chat 页面增加运行模式选择。
8. 运行端到端测试与构建检查。

## 13. 成功标准

第一阶段完成后，用户应能清楚理解并完成以下两条路径：

1. 不创建 Workflow，直接创建 Agent、配置模型、进入 Chat，自主完成任务。
2. 创建 Agent 后，为该 Agent 创建并发布 Workflow，在 Chat 中选择流程模式，让 Agent 按稳定链路处理任务。

两条路径都属于同一个 Agent 使用体验，而不是两个割裂产品。
