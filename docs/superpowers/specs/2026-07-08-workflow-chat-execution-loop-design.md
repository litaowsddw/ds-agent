# Workflow 与 Chat 执行闭环优化设计

日期：2026-07-08

## 1. 背景

上一阶段已经完成 Agent-first 产品定位：Agent 是主工作台，Workflow 是绑定到 Agent 的可选执行策略，Chat 支持自主模式和流程模式。当前第二阶段要解决的是执行体验和实现边界没有完全收口：

- Workflow Run 路由仍直接承载执行编排、节点适配和持久化，Chat 与 Worker 复用它的内部 helper，边界不清。
- 旧的内存 `WorkflowRunStore` 仍保留另一套节点执行语义，容易与数据库版路由行为分叉。
- Chat 普通接口与 SSE 接口在 Skill、Memory、Workflow mode、trace 输出上存在不同路径。
- Workflow 页面已有 Agent 语义，但操作仍是 Create / Save / Publish / Run 并列按钮，缺少“可执行流程”的步骤感和失败解释。
- Chat 页面重复 Agent 侧栏，视觉语言与主站组件不一致，流程模式阻断时缺少明确下一步。

本设计聚焦一个可测试闭环：用户选择 Agent，构建并发布 Workflow，在 Chat 或 Workflow 工作台运行，看到清晰的运行状态、节点 Trace 和可跳转的 Run 结果。

## 2. 产品原则

### 2.1 执行链路只有一条事实来源

Workflow 的同步执行、Chat 流程模式、Worker 异步执行都应通过同一个应用服务进入，不再把节点执行逻辑分散在路由、旧 store 和 worker task 中。

### 2.2 Chat 是运行入口，Runs 是审计入口

Chat 展示运行模式、最终输出和关键 Trace。节点级完整日志保留在 Workflow Runs 页面或 Workflow 工作台的 Run Trace 区域。Chat 中要给出 `workflow_run_id` 的可见入口，而不是把审计信息塞进消息气泡。

### 2.3 Workflow 工作台按状态推进

Workflow 工作台表达为“编辑草稿 -> 发布 -> 运行 -> 查看 Trace”。按钮根据当前状态禁用并解释原因，schema-only 节点在创建前就标明暂不可执行。

### 2.4 第二阶段不扩大平台边界

本阶段不重做 Agent 工作台 tabs，不实现完整 Background Agent 系统，不改认证模型，不引入新的前端 UI 框架或状态管理库。

## 3. 第一阶段目标

1. 抽出 `WorkflowExecutionService`，让 Workflow Runs 路由和 Chat workflow mode 共享同一执行入口。
2. 统一 Workflow 节点参数校验和错误模型，至少覆盖 LLM、RAG、Tool、Start、End。
3. 让 Chat 普通接口与 SSE 接口在 workflow mode 的行为和 metadata 保持一致。
4. 优化 Workflow 工作台，使用户能理解草稿、发布、运行和 Trace 的当前状态。
5. 优化 Chat 页面上下文栏和流程模式阻断态，减少重复 Agent 侧栏和灰蓝/dark 风格割裂。
6. 补充 focused contract tests，覆盖服务层、Chat workflow mode、节点错误和前端构建。

## 4. 非目标

- 不实现 Agent 自动选择 Workflow。
- 不实现所有 schema-only 节点的真实执行。
- 不重构完整 Skill lifecycle。
- 不实现 Background Agent run history。
- 不新增数据库迁移，除非现有模型缺字段导致执行闭环不可测试。
- 不做移动端完整响应式重构，只修复当前页面的明显窄屏溢出。

## 5. 后端设计

### 5.1 WorkflowExecutionService

新增服务文件：

```text
apps/api/app/services/workflow_execution.py
```

核心接口：

```python
class WorkflowExecutionService:
    async def create_and_execute(
        self,
        session: AsyncSession,
        *,
        version_id: str,
        input_data: dict[str, Any],
        actor_user_id: str,
    ) -> WorkflowRunModel:
        ...

    async def execute_existing_run(
        self,
        session: AsyncSession,
        *,
        run: WorkflowRunModel,
        definition: dict[str, Any],
        input_data: dict[str, Any],
        actor_user_id: str,
    ) -> WorkflowRunModel:
        ...
```

`create_and_execute` 负责读取 Workflow Version、校验组织权限、创建 run、同步执行、刷新并返回 run。`execute_existing_run` 负责状态更新、调用 `packages.workflow.executor.WorkflowExecutor`、持久化 node runs、保存 output/error。

### 5.2 节点适配器

`WorkflowExecutionService` 内部保留最小节点适配器：

- LLM：继续使用当前组织的 model provider 与 `LLMGateway`。
- RAG：继续调用 `search_knowledge_base`，但查询文本和 top-k 解析集中在 service 中。
- Tool：非 dict `arguments` 直接产生失败，不再静默变 `{}`。
- Start / End：继续由 `packages.workflow.executor` 处理 DAG 和输入输出。

本阶段不把适配器拆成多个文件，避免一次性重构过大；但 service 内部方法命名要让后续拆分自然。

### 5.3 路由瘦身

`apps/api/app/routes/workflow_runs.py` 保留 HTTP 责任：

- 解析请求。
- 调用 `workflow_execution_service.create_and_execute`。
- list/get/node response 转换。
- async mode 仍提交 worker，但同步执行不再在路由实现。

`apps/api/app/routes/chat.py` 的 workflow mode 调用同一个 service。普通 `chat()` 与 `chat_stream()` 都用相同的 workflow 校验函数和相同的 response metadata：

```json
{
  "execution_mode": "workflow",
  "workflow_id": "...",
  "workflow_run_id": "..."
}
```

### 5.4 错误处理

- Workflow 不属于当前 Agent：400，`Workflow 必须属于当前 Agent`。
- Workflow 未发布：400，`Workflow 必须先发布`。
- 未选择 Workflow 且无默认 Workflow：400，`请选择 Workflow 或改用自主模式`。
- Tool arguments 不是对象：run 失败并记录 node error，错误文本包含 `Tool arguments must be an object`。
- RAG knowledge base 不存在或不可访问：run 失败并记录 node error。

## 6. 前端设计

### 6.1 Workflow 工作台状态条

在 `apps/web/app/workflows/page.tsx` 中新增轻量状态条：

```text
Agent selected -> Draft saved -> Published -> Run complete
```

它不需要复杂状态机库，只根据当前 `selectedAgentId`、`selectedWorkflowId`、`selectedWorkflow.published_version_id`、`runs[0]` 推导状态。按钮文案和禁用态围绕状态条：

- 没有 workflow：只能 Create。
- 有 draft：可 Save，可 Publish；Run 需要 published version。
- 已 published：可 Run。
- Run 完成：Run Trace 显示节点日志。

### 6.2 Workflow 节点能力提示

节点 palette 保留 `live/schema` 标签。schema-only 节点按钮仍可添加，但卡片文案要明确“可设计，暂不参与真实执行”。Run 前如果存在 schema-only 节点，前端给轻量提示；真正执行失败仍以后端为准。

### 6.3 Chat 页面上下文栏

`apps/web/app/chat/page.tsx` 去掉重复的左侧 Agent 列表，改为顶部上下文栏：

- Agent selector。
- Chat / Skill Evolver tabs。
- 当前 Agent 的 Workflow 数量和默认 Workflow 简短提示。

`ChatPanel` 只负责消息、执行模式和 trace，不再承担 Agent 列表。

### 6.4 Chat 流程模式阻断态

流程模式下没有已发布 Workflow 时，显示明确提示：

```text
当前 Agent 还没有已发布 Workflow。请先到 Workflows 发布流程，或切回自主模式。
```

提供一个链接按钮到 `/workflows`。发送按钮继续禁用，但禁用原因可见，不只放在 `title`。

### 6.5 Trace 从消息气泡中拆出

`ThinkingTrace` 从最后一个 assistant bubble 下方移动到输入区上方或右侧独立区域。本阶段采用输入区上方可折叠 panel，避免改全局布局：

- 运行中显示当前事件。
- 完成后显示最近 5 个关键事件。
- workflow mode 完成后显示 `workflow_run_id` 和查看 Runs 的入口。

## 7. 数据流

### 7.1 Workflow 工作台运行

```text
User clicks Run
  -> POST /workflow-runs
  -> WorkflowExecutionService.create_and_execute
  -> WorkflowExecutor
  -> node_runs persisted
  -> run output/error persisted
  -> frontend refreshes runs and node runs
```

### 7.2 Chat 流程模式

```text
User message
  -> POST /chat/stream
  -> resolve workflow by explicit id or agent default
  -> WorkflowExecutionService.create_and_execute
  -> session user/assistant messages persisted
  -> SSE emits workflow trace and final response
```

## 8. 测试策略

### 8.1 后端

- Service 层：`create_and_execute` 创建 run、执行成功、持久化 node runs。
- Service 层：Tool arguments 非对象时 run 失败并记录 node error。
- Chat：普通 workflow mode 和 stream workflow mode 都保存相同 metadata。
- Chat：跨 Agent Workflow 仍拒绝。
- Workflow Runs：同步 API 继续通过既有 e2e tests。

### 8.2 前端

- TypeScript build 必须通过。
- ChatPanel 的 workflow blocked reason 必须是可见文本。
- Workflows page 的状态条和按钮禁用逻辑通过类型检查；如项目没有前端测试框架，本阶段不新增测试框架。

## 9. 实施顺序建议

1. 后端抽出 `WorkflowExecutionService`，保持 API 行为不变。
2. 增加节点错误 contract test，收紧 Tool arguments 校验。
3. Chat workflow mode 复用服务和公共 metadata helper。
4. Workflow 工作台状态条与按钮禁用态。
5. Chat 顶部上下文栏、阻断态和独立 trace panel。
6. 运行 focused backend tests 与 `npm run build`。

## 10. 成功标准

完成后，用户应能清楚完成以下闭环：

1. 在 Workflows 页面看到当前 Agent、草稿/发布状态和可执行条件。
2. 发布 Workflow 后在 Workflow 工作台运行，并看到节点 Trace。
3. 在 Chat 中选择流程模式，如果没有已发布 Workflow 能看到明确下一步。
4. 在 Chat 流程模式运行后，assistant message metadata、SSE final event 和 Workflow Run 记录指向同一个 `workflow_run_id`。
5. 后端 Workflow 执行逻辑由一个服务统一承载，路由不再直接实现节点执行细节。
