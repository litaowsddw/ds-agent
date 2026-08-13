# 当前开发状态

## v0.7 模型选择器 + Supervisor 工具契约 + Workflow 审批续跑（2026-08-13）

- **模型选择器（后端）**：`ChatRequest` 增加 `model_provider/model_name` override；
  `build_chat_llm_stack` 与 `_build_chat_llm_stack` 支持本轮临时替换模型（供应商必须
  在该组织已配置且启用）；`/chat/` 与 `/chat/stream` 全路径透传。
- **模型选择器（前端）**：ChatPanel 增加模型下拉（按 Agent 记忆到 localStorage），
  sendMessage/streamChat 透传 `model_provider/model_name`。
- **Supervisor 工具契约增强**：`system_prompt.py` 新增 `SUPERVISOR_TOOL_CONTRACT`
  （只读工具集 + 最小能力调用 + 结果作为证据报告），注入 Supervisor 的 plan/reflect
  系统提示词。
- **默认系统工具扩充（安全读集）**：新增 `knowledge_list` 工具（列举组织知识库元数据，
  不返回文档内容），`build_supervisor_tools` 现装配 knowledge_list / knowledge_search /
  memory_recall / skill_search / workspace_read；高风险 MCP 仍走 Workflow 审批路径。
- **Workflow 审批后续跑**：新增 `POST /workflow-runs/{run_id}/resume`。审批通过后的
  `awaiting_manual_resume` 运行可续跑：已成功节点输出被预置为 `resume_state` 并跳过重复
  执行，仅执行暂停点之后的下游节点并落盘，最终收敛为 `succeeded`/`failed`。

## v0.6 管线收敛与语义检索（2026-08-12）

- **Chat 双路径收敛**：`/chat/` 不再有独立的会话/网关/执行栈，改为流通
  `_chat_stream_events` 的薄适配器（记录状态码透传），stream 与 non-stream 编排
  完全同路径；supervisor kind 映射为 `mode="supervisor"`；workflow 模式响应不变
- **语义 Embedding 上线**：新增 `OpenAICompatibleEmbeddingProvider`
  （`AGENTFLOW_EMBEDDING_PROVIDER=openai-compatible`），生产启用
  `text-embedding-v4`（dim 1024，归一化后 IP 度量等价 cosine）；
  新增兼容 `provider_id/provider_key` 的供应商解析；`.env.example` 文档化
- **存量索引迁移**：14 篇存量文档已用新 embedding 重建进新 Milvus 集合
  `agentflow_knowledge_chunks_te_v4`（相关/无关查询区分度从哈希级跃升为语义级
  e.g. 0.369 vs 0.12-0.24）
- **生产修复**：内置 skill（`bdl_*`）不再写 `skill_evaluations`（外键失败导致 500）

## v0.5.1 波次 3：性能与结构（2026-08-12）

- **Provider 全量 httpx 化**：`OpenAICompatibleProvider` 迁移到 `httpx.AsyncClient`（连接池复用），
  消除 urllib 同步阻塞；Gateway 增加 `sync/async provider 兼容`（`_await_maybe`）与
  `同步/异步流式迭代器统一消费 + 显式关闭`（`_aiter_provider_chunks`）
- **计量独立事务**：`SessionUsageRecorder.record_terminal` 改为独立短 session + 独立 commit，
  请求失败/断流不再丢失已发生的计费事实
- **可观测接电**：`LLMGateway.generate/stream_generate` 埋点 LLM 指标（调用数/耗时/Tokens/错误），
  HTTP 中间件埋点 API 指标；`call_logs` 改有界 `deque(maxlen=500)`；`/metrics` 产出真实数据
- **路由去阻塞**：knowledge embedding/文档解析、MCP 工具发现、chat RAG 工具的
  同步 I/O 统一 `asyncio.to_thread` 移出事件循环
- **健康检查分层**：`/health`（liveness）与 `/health/ready`（MySQL/Redis 依赖连通性）
- **生产修复**：内置 skill（`bdl_*`）不再写入 `skill_evaluations`（外键约束失败导致
  命中内置 skill 的 chat 500）
- `requirements.txt` 新增 `httpx==0.28.1`

## v0.5 安全收口与工具链通电（2026-08-12）

- **ReAct 工具循环通电**（此前生产从未工作）：
  - `LLMCallResponse.raw` 现包含供应商响应的 `choices`（`gateway/llm.py`）
  - `GatewayChatModel` 读取属性名修正为 `raw`（此前读不存在的 `raw_response`，tool_calls 永远为空）
  - `langgraph_supervisor` 增加 `_normalize_subtasks`：容忍 LLM 输出字符串列表/缺字段的子任务
- **认证统一收口**：约 30 个端点从 `actor_user_id` 明文自报改为 `AuthenticatedUser`/`CurrentUser`
  + `resolve_actor`（生产强制 JWT，开发期 body/query actor 降级兼容）；
  删除越权端点 `GET /model-providers/{id}/decrypted-key`；
  `/chat/sessions/{id}/messages`、`/evolver/*` 等裸奔端点已加成员校验；
  model_providers 读写增加组织成员校验
- **双导入根统一**：`app/__init__.py` 安装 meta-path finder，`app.*` 与 `apps.api.app.*`
  归一为单实例（此前 llm_gateway/限流器/缓存双实例）；删除 `workflow_runs.py` 三处猴子补丁
- **Evolver 链修通**：补齐 `sync_session_factory`；routes/worker 均按组织 provider 配置真实
  构建 `SkillEvolverLLMCaller`（此前构造即抛）；修复 `SkillEvoverLLMCaller` 拼写 NameError
- **Agent kind 对齐**：`AgentCreateRequest`/`AgentUpdateRequest` 暴露 `kind`（此前 API 无法创建
  SUPERVISOR Agent——Supervisor 能力完全不可达），白名单校验
- **体验修复**：
  - provider 引用兼容 provider_id/provider_key，报错如实化并给出行动指引
  - `/workflow-runs` 无过滤条件时按 JWT 组织过滤（不再静默返回空列表）
  - Agent 未配置模型的错误信息改为可行动的中文指引
- **evolver 审批**：请求体增加 `org_id` 用于审批权限校验（前端 EvolverPanel 已同步）

生产验证（2026-08-12，deepseek-v4-pro 真实调用）：Supervisor Agent 经 `/chat/` 完成
plan → delegate → ReAct（多次 `knowledge_search` 工具调用）→ reflect → respond 全链路，
检索结果命中知识库 chunk 并正确汇报分数。

## v0.4 运行时收敛与清理（2026-08-11）

- **Supervisor 断链修复**：`/chat/` 与 A2A Task 现在为 Supervisor 构建真实的
  `GatewayChatModel`（此前只注入文本调用器，导致规划永远走规则降级、子任务全部失败）。
- **默认系统工具接入**：`/chat/` 的 Supervisor SubAgent 默认装配 `knowledge_search` /
  `memory_recall` / `skill_search`（`packages/runtime/tools/registry.py`，opencode 风格
  注册表）；高风险 MCP 工具仍走 Workflow 审批路径。
- **LangGraph 单一执行路径**：删除 legacy `supervisor.py` / `execution_engine.py` /
  `session_router.py`；`AgentRuntime` 不再保留双模式。
- **死代码清理**：删除 12 个已被 `services/db/*` 取代的进程内存 store
  （`agent_store` / `identity_store` / `session_store` / `workflow_store` /
  `workflow_run_store` / `skill_store` / `mcp_store` / `memory_store` /
  `knowledge_store` / `model_provider_store` / `background_agent_store` /
  `storage/local_state.py`）及对应的内存实现测试；删除 runtime 桩模块
  （`memory_manager` / `mcp_registry` / `skill_registry`）。
- **A2A 修复**：`Depends(get_db_session)` 空依赖、错误的 session 写入 API、未提交事务、
  硬编码 `base_url`（改 `AGENTFLOW_PUBLIC_BASE_URL`）均已修复；异步 Task 明确返回 501。
- **平台内置 Skill**：`apps/api/app/assets/skills/*/SKILL.md` 经
  `services/bundled_skills.py` 加载，对全部组织默认可用（当前内置 `workflow-builder`）。
- **前缀缓存观测**：`GatewayChatModel` 调用现在携带系统提示词的 `prefix_hash`，
  计量侧可按前缀聚合缓存表现（Reasonix 风格）。
- **反馈循环修复**：`evolution_records` 默认值为类的 bug、冷却时间从未写入的 bug 已修复，
  新增 `packages/runtime/tests/test_feedback_loop.py` 门控测试。
- **生产 schema 管理**：`APP_ENV=production` 时启动只做 Alembic 版本一致性校验并告警，
  不再 `create_all`；CORS 来源改由 `AGENTFLOW_CORS_ORIGINS` 配置。

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
