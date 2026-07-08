# AgentFlow 项目结构说明

## 1. 顶层目录

```text
AgentFlow/
  apps/
    api/        后端 API 服务 (FastAPI + SQLAlchemy + MySQL)
    worker/     Celery Worker 服务 (Redis broker)
    web/        Next.js 前端 (Dify 风格 UI)
  packages/
    runtime/    Agent Runtime 抽象 (Supervisor/SubAgent)
    workflow/   Workflow DSL 与执行逻辑
    a2a/        A2A Agent Card 外部发现
    shared/     前后端共享类型和常量
  docs/         中文项目文档
  tests/        跨服务集成测试
```

## 2. apps/api

后端 API 服务，使用 FastAPI + SQLAlchemy + MySQL + Redis。

```text
apps/api/
  app/
    main.py              FastAPI 应用入口（生命周期管理）
    database.py          SQLAlchemy 异步/同步引擎 + 会话工厂
    core/
      security.py        密码哈希和验证
      redis.py           Redis 异步客户端封装
    models/              SQLAlchemy ORM 模型 (17 个表)
      identity.py        User, Organization, Team, Membership, AuditLog
      agent.py           Agent, AgentWorkspace
      session.py         Session, SessionMessage
      runtime.py         Skill, MCP, Memory, ModelProvider, BackgroundAgent
      workflow.py        Workflow, Version, Run, NodeRun, KB, Document, Chunk
    services/
      db/                数据库服务层
        base.py          通用 CRUD 基类（分页、过滤、计数）
        identity_db.py   用户与组织
        agent_db.py      Agent 与 Workspace
        session_db.py    Session 与消息
        workflow_db.py   Workflow/Run/KB
        runtime_db.py    Skill/MCP/Memory
      redis_cache.py     Redis 结果缓存
    routes/              API 路由（全部使用 DB 服务 + 依赖注入）
      agents.py, workflows.py, sessions.py, identity.py
      workflow_runs.py, knowledge.py, gateway.py, cache.py
      ws.py              WebSocket/SSE 实时推送
    gateway/
      llm.py             LLM Gateway（异步 Redis 限流）
      rate_limiter.py    Redis Lua 全局令牌桶 + 混合限流
  alembic/               数据库迁移
```

## 3. apps/worker

Celery Worker 服务，使用 Redis broker。

```text
apps/worker/
  app/
    celery_app.py        Celery 配置（Redis 连接池 + 序列化）
    tasks/
      workflow.py        Workflow 执行（DB 状态更新 + 缓存失效）
      background.py      后台 Agent 任务
```

## 4. apps/web

Next.js 前端，Dify 风格 UI。

```text
apps/web/
  app/                   Next.js App Router 页面
  components/
    layout/              Sidebar, Header, AppLayout
    nodes/               React Flow 自定义节点 (Start/End/LLM/RAG/Tool)
    ui/                  Panel, Form, Button, DataDisplay
  stores/                Zustand 状态管理
    workspace.ts, workflow.ts, runtime.ts, knowledge.ts
  types/                 TypeScript 类型定义
  lib/                   api.ts, websocket.ts, constants.ts
```

## 5. packages/runtime

Agent Runtime 核心，支持 Supervisor/SubAgent 架构。

```text
packages/runtime/
  agent_runtime.py       Agent 运行时
  supervisor.py          Supervisor Agent (spawn/announce/settle)
  subagent.py            SubAgent Registry + 系统工厂
  session_router.py      Session 路由映射
  context_engine.py      Context Engine
  prompt_compiler.py     Prompt Compiler
  skill_registry.py      Skill Registry
  mcp_registry.py        MCP Registry
  memory_manager.py      Memory Manager
```

## 6. packages/workflow

Workflow DSL 与执行逻辑。

Workflow 属于 Agent 的可选执行策略。所有 Workflow 都绑定 `agent_id`，用于在需要稳定流程时约束 Agent 的执行链路；自主 Agent 对话不依赖 Workflow。

```text
packages/workflow/
  dsl.py                 Workflow DSL 定义
  executor.py            Workflow 执行器
  validator.py           DAG 校验器
```

## 7. packages/a2a

A2A Agent Card 外部发现模块。

```text
packages/a2a/
  agent_card.py          AgentCard 元数据模型
  routes.py              A2A 端点 (GET /card, POST /tasks)
```

## 8. 基础设施

```text
docker-compose.yml       MySQL 8.0 + Redis 7 + Milvus + MinIO + etcd
.env.example             环境变量模板
```

## 9. 数据库表一览

| 表名 | 说明 |
|------|------|
| users | 用户 |
| organizations | 组织 |
| teams | 群组 |
| memberships | 成员关系 |
| audit_logs | 审计日志（append-only）|
| agents | Agent（含 kind/model_provider）|
| agent_workspaces | Agent Workspace |
| sessions | Agent 会话 |
| session_messages | 会话消息（append-only）|
| skills | Skill |
| agent_skill_policies | Agent Skill 授权策略 |
| mcp_servers | MCP Server |
| mcp_tools | MCP Tool |
| agent_mcp_policies | Agent MCP 授权策略 |
| memories | Memory 记忆 |
| model_providers | 模型供应商配置 |
| background_agents | 后台 Agent 配置 |
| workflows | Workflow |
| workflow_versions | Workflow 版本（不可变）|
| workflow_runs | Workflow 运行 |
| node_runs | 节点运行日志 |
| knowledge_bases | 知识库 |
| documents | 文档 |
| chunks | 文档块 |
