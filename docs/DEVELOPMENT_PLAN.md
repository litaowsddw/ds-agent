# AgentFlow 完整项目开发计划

## 1. 项目目标

AgentFlow 的目标是建设一个开源 Agent 框架：

- 前端以 Agent 工作台为主入口，支持创建、配置、对话和观测 Agent；可视化 Workflow 作为 Agent 的可选流程策略。
- 单 Agent 不依赖 Workflow 即可运行；Workflow 用于需要稳定输入输出、可复现执行和节点级审计的场景。
- 后端参考 OpenClaw 的运行时思想，实现 Agent Gateway、上下文管理、MCP 服务、Skill 组织、内存管理和后台 Agent 服务。
- 异步执行采用 Celery + Redis，支持高并发任务排队、优先级、重试、超时控制。
- 核心架构采用异步任务队列、工作流隔离、资源限流、全局令牌桶限流。
- 缓存设计参考 DeepSeek Reasonix 的 prefix-cache 友好思想，同时提供平台级结果缓存。
- 项目按 MVP 原则拆分模块，每个模块单独开发、单独测试，最后联合测试。
- 代码使用 GitHub 管理，通过 Issue、Milestone、PR、CI 保证工程质量。

## 2. 技术栈确定

### 2.1 前端技术栈

| 类型 | 技术 |
| --- | --- |
| Web 框架 | Next.js + React + TypeScript |
| 工作流画布 | React Flow |
| UI 样式 | Tailwind CSS |
| 状态管理 | Zustand / TanStack Query |
| 表单校验 | React Hook Form + Zod |
| 实时状态 | WebSocket / Server-Sent Events |
| 测试 | Vitest + Testing Library + Playwright |

### 2.2 后端技术栈

| 类型 | 技术 |
| --- | --- |
| API 框架 | FastAPI |
| 数据库 | PostgreSQL |
| ORM | SQLAlchemy 2.x |
| 迁移 | Alembic |
| 任务队列 | Celery |
| Broker / Result Backend | Redis |
| 限流与缓存 | Redis + Lua |
| 向量检索 | MVP 使用 pgvector |
| 对象存储 | MinIO / S3 兼容存储 |
| 可观测性 | OpenTelemetry + Prometheus + Grafana |
| 测试 | pytest + httpx + pytest-asyncio |

### 2.3 运行时与网关技术栈

| 模块 | 技术方向 |
| --- | --- |
| Agent Gateway | FastAPI 内部模块起步，后续可拆独立服务 |
| Context Engine | Python 模块，负责上下文 ingest / assemble / compact / after_turn |
| Skill Registry | `SKILL.md` 文件模型 + 数据库存储 |
| MCP Registry | HTTP/SSE/Streamable HTTP MCP Client 起步 |
| Memory Manager | PostgreSQL + pgvector + Redis 热缓存 |
| Background Agent | Celery Beat + Celery Worker |
| Prompt Compiler | 稳定序列化、prefix hash、token 统计 |

## 3. 总体架构

```text
用户浏览器
  -> Next.js 前端
  -> FastAPI API Layer
  -> Gateway Layer
  -> Agent Runtime Layer
  -> Workflow Layer
  -> Celery Task Layer
  -> PostgreSQL / Redis / Object Storage
```

### 3.1 API Layer

负责用户请求入口：

- 登录注册。
- 组织、群组、成员管理。
- Agent 管理。
- Workflow 管理。
- Session 管理。
- Run 查询。
- 前端实时事件推送。

### 3.2 Gateway Layer

负责统一出口和控制面：

- 鉴权。
- 限流。
- 审计。
- LLM Provider 调用。
- RAG 调用。
- Tool 调用。
- MCP 调用。
- 缓存读写。
- 成本统计。

### 3.3 Agent Runtime Layer

参考 OpenClaw 思路，负责长期运行的 Agent 能力：

- Workspace 管理。
- Session 管理。
- Context Engine。
- Skill Registry。
- MCP Registry。
- Memory Manager。
- Prompt Context Compiler。
- Background Agent Manager。

### 3.4 Workflow Layer

负责可视化工作流的执行逻辑：

- Workflow DSL。
- DAG 校验。
- 节点执行。
- 运行状态机。
- 节点日志。
- 失败重试。
- 结果输出。

### 3.5 Task Layer

负责异步调度：

- Celery 队列。
- Redis Broker。
- 任务优先级。
- 任务超时。
- 任务取消。
- 并发控制。
- 后台 Agent 服务。

## 4. 核心领域模型

### 4.1 多租户隔离模型

所有核心资源必须绑定：

```text
org_id
team_id 可选
created_by
created_at
updated_at
```

隔离边界：

- 用户只能访问所属组织资源。
- Agent 只能访问授权 Workflow、Skill、MCP、Knowledge Base。
- Workflow Run 只能读取同组织下的上下文和密钥。
- Provider Credential 必须按组织加密存储。

### 4.2 Agent Runtime 模型

每个 Agent 拥有独立运行时：

```text
AgentRuntime
  Workspace
  Sessions
  Skills
  MCP Servers
  Memories
  Runtime Policy
  Gateway Policy
```

### 4.3 Workflow 模型

Workflow 使用版本化 JSON DSL：

```json
{
  "version": "1.0",
  "nodes": [],
  "edges": []
}
```

发布版本不可变，草稿可编辑。

## 5. Reasonix 风格缓存友好设计

DeepSeek Reasonix 的核心启发是 prefix-cache 友好的上下文组织，而不是单纯的结果缓存。

### 5.1 Prompt 分层

```text
Immutable Prefix
  系统规则
  Agent 系统提示词
  Workflow 版本说明
  稳定 Tool Schema
  稳定输出契约

Append-only Log
  历史消息
  历史工具调用摘要
  历史节点摘要

Current Turn
  当前用户输入
  当前节点输入
  RAG 召回内容
  当前运行约束
```

### 5.2 稳定性要求

- JSON 序列化必须字段顺序稳定。
- 工具列表必须排序稳定。
- Skill 列表必须排序稳定。
- Workflow 节点说明必须绑定版本。
- 临时 scratch 状态不能进入 Prompt。
- 每次 LLM 调用记录 prefix hash。
- 采集 provider 返回的 cache hit tokens。

### 5.3 平台级结果缓存

缓存对象：

- LLM 响应。
- Embedding。
- RAG 检索。
- Tool 调用。
- 节点输出。
- 子工作流输出。

## 6. MVP 模块拆分

### 模块 1：项目骨架与基础设施

目标：

- 建立 monorepo。
- 建立 Docker Compose。
- 建立 FastAPI、Next.js、Celery、Redis、PostgreSQL 基础服务。
- 建立 GitHub Actions。

验收：

- 本地服务可启动。
- API health check 正常。
- Worker 可执行 smoke task。
- 前端首页可访问。

### 模块 2：用户、组织、群组、权限隔离

目标：

- 用户注册登录。
- 组织、群组、成员关系。
- RBAC 权限。
- 审计日志。

验收：

- 用户只能访问自己组织的数据。
- 管理员可以管理成员。
- viewer 不能创建资源。

### 模块 3：Agent 管理与 Workspace

目标：

- 创建 Agent。
- Agent 绑定组织和群组。
- Agent 拥有独立 Workspace。
- Workspace 支持 AGENTS、SOUL、TOOLS、MEMORY 文件。

验收：

- Agent 不能跨组织访问 Workspace。
- Workspace 可保存和读取。
- Agent Runtime 可加载 Workspace。

### 模块 4：Session Manager 与消息存储

目标：

- 创建 Session。
- 保存消息。
- 支持 queue / collect 模式。
- 支持恢复历史。

验收：

- Session 可跨请求恢复。
- 消息按 append-only 保存。
- 上下文构建不改写原始消息。

### 模块 5：Context Engine MVP

目标：

- 实现 ingest / assemble / compact / after_turn 生命周期。
- 支持 token budget。
- 支持上下文分层。

验收：

- assemble 输出结构化上下文。
- 超过预算时可截断。
- compact 只新增摘要，不删除原始历史。

### 模块 6：Skill Registry MVP

目标：

- 支持 `SKILL.md`。
- 支持 Agent / Team / Org / Bundled 多级 Skill。
- 支持 allowlist。

验收：

- Agent 只看到授权 Skill。
- 默认只注入 Skill 摘要。
- 选中 Skill 后再加载全文。

### 模块 7：MCP Registry MVP

目标：

- 注册 MCP Server。
- 支持 HTTP/SSE/Streamable HTTP。
- 读取 tool schema。
- Agent 授权后调用。

验收：

- MCP Server 按组织隔离。
- MCP 调用经过 Gateway。
- 大结果写 artifact，不直接塞入上下文。

### 模块 8：Workflow DSL 与版本管理

目标：

- 定义 Workflow JSON Schema。
- 实现 DAG 校验。
- 草稿、发布、回滚。

验收：

- 非法 DAG 不可发布。
- 发布版本不可变。
- 历史版本可读取。

### 模块 9：可视化工作流编辑器

目标：

- React Flow 画布。
- 节点拖拽。
- 节点配置面板。
- 保存和发布。

验收：

- 可搭建 Start -> LLM -> End。
- 配置可持久化。
- 发布前显示校验错误。

### 模块 10：Celery 工作流执行引擎

目标：

- 异步运行 Workflow。
- 节点拓扑执行。
- 记录 Workflow Run 和 Node Run。

验收：

- 可异步运行工作流。
- 每个节点有状态、输入、输出、耗时。
- 失败可重试或终止。

### 模块 11：Gateway + LLM Provider

目标：

- OpenAI-compatible Provider。
- 密钥按组织隔离。
- 调用审计。
- token 和成本统计。

验收：

- Worker 只能通过 Gateway 调用 LLM。
- Provider 错误统一标准化。
- 调用日志完整。

### 模块 12：Prompt Context Compiler

目标：

- 稳定序列化 Prompt。
- 生成 prefix hash。
- 支持 Reasonix 风格 prefix-cache 友好结构。

验收：

- 相同 Agent/Workflow 的 immutable prefix 字节一致。
- 临时 scratch 不进入 Prompt。
- cache hit token 指标可记录。

### 模块 13：全局限流与并发控制

目标：

- Redis Lua token bucket。
- Redis semaphore。
- org/user/agent/provider/model 多维限流。

验收：

- 多 worker 下全局限流有效。
- 超限任务不会打到外部 provider。
- 限流事件可观测。

### 模块 14：Memory Manager MVP

目标：

- Session Memory。
- Working Memory。
- Long-term Memory。
- Artifact Memory。

验收：

- 记忆按 org/agent 隔离。
- 可召回相关记忆。
- 敏感信息默认不进入长期记忆。

### 模块 15：RAG MVP

目标：

- 知识库。
- 文档上传。
- 切分。
- Embedding。
- pgvector 检索。

验收：

- 文档可索引。
- RAG 节点可召回。
- 知识库变更后缓存失效。

### 模块 16：传统结果缓存

目标：

- LLM 结果缓存。
- Embedding 缓存。
- RAG 缓存。
- Tool 缓存。
- Node Output 缓存。

验收：

- 相同输入可命中。
- 版本变更可失效。
- 前端显示 hit/miss。

### 模块 17：后台 Agent 服务

目标：

- Memory Agent。
- MCP Health Agent。
- Workflow Monitor Agent。
- Queue Governor Agent。

验收：

- 后台 Agent 走独立队列。
- 每类 Agent 有 runtime policy。
- 操作写审计日志。

### 模块 18：联合测试与压测

目标：

- 多用户、多组织、多 Agent 联调。
- 高并发任务压测。
- 限流压测。
- 缓存命中测试。

验收：

- 1000 个异步任务可排队执行。
- LLM 限流生效。
- 租户隔离无越权。
- 工作流执行轨迹完整。

## 7. GitHub 管理计划

### 7.1 分支

```text
main        稳定分支
develop     集成分支
feature/*   功能分支
fix/*       修复分支
release/*   发布分支
```

### 7.2 Milestone

| 版本 | 范围 |
| --- | --- |
| v0.1 | 项目骨架、API、Worker、前端基础 |
| v0.2 | 用户、组织、权限 |
| v0.3 | Agent Runtime、Workspace、Session |
| v0.4 | Context、Skill、MCP |
| v0.5 | Workflow DSL、编辑器、执行引擎 |
| v0.6 | Gateway、LLM、Prompt Compiler |
| v0.7 | 限流、内存、RAG、缓存 |
| v1.0 | 联调、压测、文档、首个稳定版 |

### 7.3 PR 要求

每个 PR 必须包含：

- 需求背景。
- 实现说明。
- 测试说明。
- 风险说明。
- 相关文档更新。

## 8. 测试策略

| 类型 | 工具 | 范围 |
| --- | --- | --- |
| 后端单元测试 | pytest | 权限、DSL、Context、缓存、限流 |
| API 测试 | httpx | 登录、Agent、Workflow、Run |
| Worker 测试 | pytest + Celery | 任务执行、重试、超时 |
| 前端单元测试 | Vitest | 组件和状态 |
| E2E | Playwright | 创建工作流、运行、查看日志 |
| 压测 | k6 / Locust | 队列、限流、并发 |
| 安全测试 | 自定义用例 | 租户隔离、密钥访问 |

## 9. 中文注释与文档要求

- 所有新增代码必须优先保证可读性。
- 复杂变量必须有中文注释说明用途。
- 复杂函数必须有中文 docstring。
- 重要模块必须配套中文文档。
- 对外 API 必须写清请求、响应、权限和错误码。
- 每个模块完成后更新 `docs/PROJECT_STRUCTURE.md` 和模块说明文档。

