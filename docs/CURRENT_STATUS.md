# 当前开发状态

## Gateway usage metering release notes

The current feature branch includes organization-scoped Gateway usage metering
and an administrator-facing Insights screen. It records provider-reported token
fields per API, provider, model, Agent, workflow, and run when that data is
available. Missing provider fields remain unknown rather than being converted
to zero or character-count estimates.

This is a metering/observability capability, not a billing system. Optional
estimated cost values use configured price cards only; they are not invoices,
credit debits, token-budget enforcement, or a source of truth for a provider
charge. Provider cache-read tokens, platform cache metrics, and stable-prefix
eligibility are independent signals. In particular, an eligible stable prefix
does not prove a provider cache hit.

### Operational rollout

1. Back up the database and run Alembic revision `20260714_0002` in staging.
2. Verify the `/metering` API with an organization billing administrator and
   confirm that cross-organization queries are denied.
3. Deploy the API and Insights UI together, then watch the known/unknown usage
   and provider-cache-reporting coverage before relying on aggregate trends.
4. Roll back application code only with a compatible schema. The migration
   downgrade drops metering history, so use it only after a verified backup and
   an explicit data-retention decision.

## 产品主线

当前产品主线收敛为 Agent 构建与运行平台。Agent 默认可自主处理任务；Workflow 绑定到 Agent，作为可选执行策略提供稳定输入输出和流程审计。

## 已完成

### Sprint 0：前端重构（Dify 风格 UI）✅

- **项目结构重组**：创建 `types/`, `lib/`, `stores/`, `components/` 目录
- **TypeScript 类型定义**：`types/agent.ts`, `types/workflow.ts`, `types/runtime.ts`, `types/knowledge.ts`, `types/api.ts`
- **API 客户端**：`lib/api.ts` — 统一封装 fetch 请求和错误处理
- **WebSocket 客户端**：`lib/websocket.ts` — WebSocket/SSE 实时通信
- **常量定义**：`lib/constants.ts` — 导航项、节点面板、初始画布节点
- **Zustand 状态管理**：
  - `stores/workspace.ts` — 工作空间、Agent 列表、API 状态
  - `stores/workflow.ts` — 画布节点/边、Workflow CRUD、运行 + WebSocket 实时更新
  - `stores/runtime.ts` — Skill、MCP、Memory、Session、Gateway
  - `stores/knowledge.ts` — 知识库、文档、检索
- **Dify 风格全局布局**：Sidebar + Header + AppLayout + Toast
- **自定义 React Flow 节点**：Start/End/LLM/RAG/Tool 5种节点
- **页面拆分**：首页、Agent、Workflow、Runtime、Knowledge、Runs、Chat

### Sprint 1：数据层 + Runtime 架构 ✅

- **MySQL + SQLAlchemy ORM 模型**：17 个表
- **Supervisor + SubAgent 架构**：spawn/announce/settle 机制
- **A2A Agent Card 外部发现**：符合 Google A2A 规范
- **Alembic 迁移配置**

### Sprint 2：Redis + 数据库服务 + 路由迁移 ✅

- **Redis 集成**：异步客户端 + Lua 全局限流 + 混合缓存
- **数据库服务层**：7 个异步 CRUD 服务文件
- **API 路由迁移**：9 个路由文件使用 SQLAlchemy 异步 + 依赖注入
- **Worker 升级**：Redis broker + 数据库状态更新
- **LLM Gateway 升级**：异步 Redis 限流
- **知识库集成**：Milvus 向量检索 + 关键词降级

### Sprint 3：Supervisor A2A + Harmes 自我进化 ✅

#### Supervisor Agent A2A 升级

- **`packages/runtime/supervisor.py`** — LLM 驱动的意图理解 + 任务分解
  - `plan()` 接入 LLM Gateway 做真正的意图理解和任务分解
  - `reflect()` ReAct 反思循环：评估子任务结果，决定是否需要后续行动
  - 支持并行/串行子任务（`execution_order` + `depends_on`）
  - 降级到规则路由（LLM 不可用时）
  - 最大反思轮数限制（3 轮）

- **`packages/runtime/llm_caller.py`** — LLM 调用适配器
  - `LLMCallerAdapter` — 将 LLMGateway 适配为 runtime 层的 LLMCaller 协议
  - `SkillEvolverLLMCaller` — Skill Evolver 专用 LLM 调用器（含专用 system prompt）

- **`packages/runtime/execution_engine.py`** — SubAgent 执行引擎
  - 真正驱动 SubAgent 完成任务（通过 LLM Gateway）
  - 构建 SubAgent 上下文（system_prompt + Skill + Memory + MCP Tool）
  - 支持并行/串行执行（`execute_sync`）
  - 结果回调协议

- **`packages/runtime/agent_runtime.py`** — AgentRuntime 数据库对接
  - `chat()` 方法：Supervisor 执行完整 plan → execute → reflect → aggregate 循环
  - 普通 Agent 直接 LLM 调用
  - 对接数据库保存消息

- **A2A 协议升级**（`packages/a2a/routes.py`）
  - Agent Card 从数据库读取
  - A2A Task 对接 AgentRuntime 真正执行（同步/异步）
  - 支持追加消息（announce 语义）

- **Celery 异步任务**（`apps/worker/app/tasks/subagent.py`）
  - `execute_subagent_task` — 异步执行单个 SubAgent
  - `batch_execute_subagents` — 批量执行（按 order 分组并行）
  - `supervisor_run_cycle` — 完整 Supervisor 运行周期

#### Harmes Skill Evolver 自我进化

- **`packages/runtime/skill_evolver.py`** — 核心进化引擎
  - Analyze：分析 Agent 运行历史（LLM 驱动 + 规则降级）
  - Reflect：识别改进机会（新 Skill / 更新 Skill / 废弃 Skill / 合并 Skill）
  - Evolve：LLM 生成/更新 SKILL.md
  - Validate + Deploy：应用进化到数据库
  - 进化历史追踪 + 版本管理

- **`packages/runtime/feedback_loop.py`** — 反馈循环调度器
  - 自动模式：所有进化自动应用
  - 半自动模式：高置信度（≥0.8）自动，低置信度需审批
  - 手动模式：全部需要审批
  - 冷却时间 + 最大进化数限制 + 失败回滚

- **API 路由**（`apps/api/app/routes/evolver.py`）
  - `POST /evolver/trigger` — 触发进化
  - `GET /evolver/analysis/{agent_id}` — 运行分析
  - `GET /evolver/history/{agent_id}` — 进化历史
  - `GET /evolver/pending` — 待审批列表
  - `POST /evolver/approve` — 审批/拒绝进化
  - `GET /evolver/feedback-loop/{agent_id}` — 完整反馈循环

- **Celery 定时任务**（`apps/worker/app/tasks/evolver.py`）
  - `run_evolution_cycle` — 单 Agent 进化
  - `batch_evolution` — 批量进化（Celery Beat 调度）
  - `run_feedback_loop` — 反馈循环

#### Chat 面板 + 前端交互

- **Chat API 路由**（`apps/api/app/routes/chat.py`）
  - `POST /chat/` — 与 Agent 对话（Supervisor/普通）
  - `GET /chat/sessions/{id}/messages` — 获取会话消息

- **前端 Chat Store**（`apps/web/stores/chat.ts`）
  - `useChatStore` — Chat 对话状态管理
  - `useEvolverStore` — Evolver 进化状态管理

- **前端 Chat 页面**（`apps/web/app/chat/page.tsx`）
  - Agent 列表 + Chat/Evolver 双 Tab
  - `ChatPanel` — 消息输入/输出 + 意图/子任务状态
  - `EvolverPanel` — 触发进化/审批/查看历史/运行分析

- **前端导航更新**：添加 Chat 入口

## 下一步：Sprint 4

### 认证与安全
1. **JWT 认证中间件**：替换 actor_user_id 显式传参
2. **API Key 加密存储**：AES-256 加密 Provider API Key
3. **RBAC 细化**：基于数据库策略表的权限控制

### 可观测性
4. **OpenTelemetry 集成**：分布式追踪
5. **Prometheus 指标**：LLM 调用、缓存命中率、限流事件
6. **结构化日志**：统一日志格式和级别

### 测试
7. **后端单元测试**：数据库服务层测试
8. **API 集成测试**：完整请求生命周期测试
9. **前端 E2E 测试**：Playwright 工作流编辑器测试
