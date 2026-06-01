# AgentFlow

AgentFlow 是一个开源 Agent 工作流平台，目标是提供类似 Dify 的可视化工作流搭建体验，并在后端提供参考 OpenClaw 思路的 Agent Runtime、上下文管理、MCP 服务、Skill 组织、内存管理、后台 Agent 服务、网关、异步任务调度、限流和缓存体系。

## 当前阶段

当前仓库处于 **v0.3** 开发阶段，已完成：

### Sprint 0：前端重构（Dify 风格 UI）✅

- **项目结构重组**：`types/`, `lib/`, `stores/`, `components/` 目录
- **Zustand 状态管理**：workspace, workflow, runtime, knowledge, chat 五大 store
- **Dify 风格全局布局**：侧边栏导航 + 顶部工具栏 + 主内容区
- **自定义 React Flow 节点**：Start/End/LLM/RAG/Tool 五种自定义节点
- **页面拆分**（Next.js App Router）：
  - `/` — 首页：工作空间设置
  - `/agents` — Agent 管理
  - `/chat` — Chat 对话 + Skill Evolver
  - `/workflows` — Workflow 画布编辑器
  - `/runtime` — Runtime 管理
  - `/knowledge` — Knowledge 管理
  - `/runs` — 运行历史

### Sprint 1：数据层 + Runtime ✅

- **MySQL + SQLAlchemy 2.x** 数据层 ORM 模型定义
- **Alembic** 迁移配置
- **Supervisor Agent + SubAgent** 架构
- **A2A Agent Card** 外部发现

### Sprint 2：Redis + 数据库服务 + 路由迁移 ✅

- **Redis 集成**：异步客户端 + Lua 全局限流 + 混合缓存
- **数据库服务层**：7 个异步 CRUD 服务文件
- **API 路由迁移**：所有路由使用 SQLAlchemy 异步 + 依赖注入
- **LLM Gateway**：OpenAI-compatible Provider + 异步限流

### Sprint 3：Supervisor A2A + Harmes 自我进化 ✅

- **Supervisor Agent LLM 集成**：
  - `plan()` 接入 LLM Gateway 做意图理解 + 任务分解
  - `reflect()` ReAct 反思循环
  - 支持并行/串行子任务（execution_order + depends_on）
  - 降级到规则路由

- **SubAgent 执行引擎**：
  - `packages/runtime/execution_engine.py` — 真正驱动 SubAgent 完成 LLM 调用
  - 对接 Context Engine、Skill、MCP、Memory
  - 支持并行/串行执行

- **LLM 调用适配器**：
  - `packages/runtime/llm_caller.py` — 桥接 runtime 层和 Gateway

- **A2A 协议升级**：
  - Agent Card 从数据库读取
  - A2A Task 对接 AgentRuntime 执行（同步/异步）

- **Harmes Skill Evolver 自我进化**：
  - `packages/runtime/skill_evolver.py` — Analyze→Reflect→Evolve→Deploy 循环
  - `packages/runtime/feedback_loop.py` — 自动/半自动/手动进化策略
  - LLM 驱动的 Skill 生成/更新/废弃
  - 进化历史追踪 + 版本管理

- **Chat 面板**：
  - `/chat` 页面：Agent 列表 + Chat/Evolver 双 Tab
  - Supervisor 对话：plan → execute → reflect → aggregate
  - Evolver 交互：触发进化、审批、查看历史

## 技术栈

### 前端
- Next.js 15 + React 19 + TypeScript
- React Flow (@xyflow/react) — 可视化工作流画布
- Zustand — 状态管理
- Tailwind CSS — 样式框架

### 后端
- FastAPI + SQLAlchemy 2.x（异步） + Alembic
- MySQL 8.0 — 关系数据库
- Redis 7 — 缓存、Celery broker
- Milvus 2.6 — 向量数据库
- Celery 5 — 异步任务队列

### 运行时
- Supervisor Agent — LLM 驱动的任务规划中枢（意图理解 + ReAct 反思）
- SubAgent Execution Engine — 真正执行任务的引擎（Gateway + Celery）
- Harmes Skill Evolver — Agent 自我进化（Analyze→Evolve→Deploy）
- A2A 协议 — Agent Card 外部发现 + Task 执行

## 项目结构

```
apps/
├── api/          # FastAPI 后端
│   ├── app/
│   │   ├── database.py      # SQLAlchemy 异步引擎
│   │   ├── models/          # ORM 模型（identity, agent, session, runtime, workflow）
│   │   ├── domain/          # 领域模型（dataclass）
│   │   ├── services/        # 业务服务（DB CRUD + Redis 缓存）
│   │   │   └── db/          # 数据库异步 CRUD 服务
│   │   ├── routes/          # API 路由（含 Chat、Evolver、WebSocket）
│   │   ├── gateway/         # LLM Gateway + Redis 限流
│   │   └── core/            # Redis 客户端 + 安全工具
│   └── alembic/             # 数据库迁移
├── web/          # Next.js 前端
│   ├── app/                 # 页面（App Router，含 /chat）
│   ├── components/          # UI 组件
│   │   ├── chat/            # Chat 面板 + Evolver 面板
│   │   ├── layout/          # 全局布局
│   │   ├── nodes/           # 自定义 React Flow 节点
│   │   └── ui/              # 通用组件
│   ├── stores/              # Zustand 状态管理（含 chat.ts）
│   ├── types/               # TypeScript 类型定义
│   └── lib/                 # API 客户端、WebSocket、常量
└── worker/       # Celery Worker
    └── app/tasks/           # 异步任务（workflow, subagent, evolver）

packages/
├── runtime/      # Agent Runtime
│   ├── agent_runtime.py     # 核心 Runtime 对象（Supervisor chat 循环）
│   ├── supervisor.py        # Supervisor Agent（LLM plan + ReAct reflect）
│   ├── execution_engine.py  # SubAgent 执行引擎
│   ├── llm_caller.py        # LLM 调用适配器
│   ├── skill_evolver.py     # Harmes Skill Evolver 核心
│   ├── feedback_loop.py     # Harmes 反馈循环调度器
│   ├── subagent.py          # SubAgent 注册表
│   ├── session_router.py    # Session 路由器
│   ├── skill_registry.py    # Skill 注册表
│   ├── context_engine.py    # 上下文引擎
│   └── prompt_compiler.py   # Prompt 编译器
├── workflow/     # Workflow DSL + 执行器
└── a2a/          # A2A 协议
    ├── agent_card.py        # Agent Card 元数据
    └── routes.py            # A2A 端点（DB + Task 执行）
```

## 快速开始

```bash
# 启动基础设施
docker compose up -d mysql redis milvus

# 启动后端
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload

# 启动 Worker
cd apps/worker
celery -A app.celery_app worker -l info

# 启动前端
cd apps/web
npm install
npm run dev
```

## 文档入口

- [完整开发计划](docs/DEVELOPMENT_PLAN.md)
- [项目结构说明](docs/PROJECT_STRUCTURE.md)
- [开发规范](docs/DEVELOPMENT_GUIDE.md)
- [当前开发状态](docs/CURRENT_STATUS.md)

## 开发路线图

| Sprint | 周期 | 内容 | 状态 |
|--------|------|------|------|
| Sprint 0 | 2w | 前端重构 - Dify 风格 UI | ✅ 已完成 |
| Sprint 1 | 2.5w | 数据层 + Runtime - MySQL, Supervisor, SubAgent, A2A | ✅ 已完成 |
| Sprint 2 | 1.5w | Redis + 数据库服务 + 路由迁移 | ✅ 已完成 |
| Sprint 3 | 2w | Supervisor A2A + Harmes 自我进化 | ✅ 已完成 |
| Sprint 4 | 2w | 认证安全 + 可观测性 + 测试 | ⬜ 待开始 |
