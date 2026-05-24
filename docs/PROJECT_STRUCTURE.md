# AgentFlow 项目结构说明

## 1. 顶层目录

```text
AgentFlow/
  apps/
    api/        后端 API 服务
    worker/     Celery Worker 服务
    web/        Next.js 前端
  packages/
    runtime/    Agent Runtime 抽象
    workflow/   Workflow DSL 与执行逻辑
    shared/     前后端共享类型和常量
  docs/         中文项目文档
  infra/        基础设施配置
  tests/        跨服务集成测试
```

## 2. apps/api

后端 API 服务，负责：

- HTTP API。
- WebSocket / SSE。
- 用户请求鉴权。
- 调用 Agent Runtime。
- 创建异步任务。

规划结构：

```text
apps/api/
  app/
    main.py
    core/
    api/
    models/
    schemas/
    services/
    gateway/
    runtime/
```

## 3. apps/worker

Celery Worker 服务，负责：

- 工作流异步执行。
- 后台 Agent 服务。
- 文档索引。
- 缓存清理。

规划结构：

```text
apps/worker/
  app/
    celery_app.py
    tasks/
      smoke.py
      workflow.py
      background.py
```

## 4. apps/web

前端工作台，负责：

- Agent 管理。
- Workflow 可视化编辑。
- 运行详情。
- Context Inspector。
- 缓存与限流指标展示。

规划结构：

```text
apps/web/
  app/
  components/
  features/
  lib/
  styles/
```

## 5. packages/runtime

Agent Runtime 核心抽象，负责：

- Workspace。
- Session。
- Context。
- Skill。
- MCP。
- Memory。
- Prompt Compiler。

## 6. packages/workflow

Workflow 相关逻辑，负责：

- DSL 定义。
- DAG 校验。
- 节点协议。
- 执行器接口。

## 7. docs

所有开发文档必须使用中文。每个模块完成后需要补充：

- 模块目标。
- 目录结构。
- 核心流程。
- 数据模型。
- 测试方法。
- 常见问题。

## 8. 当前已落地文件

```text
README.md
docs/
  DEVELOPMENT_PLAN.md
  DEVELOPMENT_GUIDE.md
  PROJECT_STRUCTURE.md
  MODULE_01_FOUNDATION.md
apps/
  api/
    app/
      core/
        security.py
      domain/
        agent.py
        identity.py
        mcp.py
        memory.py
        skill.py
        session.py
        workflow.py
        workflow_run.py
      gateway/
        llm.py
        rate_limiter.py
      main.py
      routes/
        agents.py
        context.py
        gateway.py
        health.py
        identity.py
        mcp.py
        memory.py
        runtime.py
        sessions.py
        skills.py
        workflows.py
        workflow_runs.py
      schemas/
        agent.py
        identity.py
        mcp.py
        memory.py
        session.py
        skill.py
        workflow.py
        workflow_run.py
        gateway.py
      services/
        agent_store.py
        identity_store.py
        mcp_store.py
        memory_store.py
        rbac.py
        session_store.py
        skill_store.py
        workflow_store.py
        workflow_run_store.py
    tests/
      test_agent_store.py
      test_agents_api.py
      test_context_api.py
      test_health.py
      test_identity_api.py
      test_identity_store.py
      test_llm_gateway.py
      test_mcp_store.py
      test_memory_store.py
      test_rate_limiter.py
      test_session_store.py
      test_skill_store.py
      test_workflow_store.py
      test_workflow_run_store.py
  worker/
    app/
      celery_app.py
      tasks/
        smoke.py
        background.py
        workflow.py
  web/
    app/
      layout.tsx
      page.tsx
      workflows/
        page.tsx
      globals.css
    features/
      workflows/
        WorkflowEditor.tsx
packages/
  runtime/
    agent_runtime.py
    context_engine.py
    prompt_compiler.py
    skill_registry.py
    mcp_registry.py
    memory_manager.py
  workflow/
    dsl.py
    executor.py
    validator.py
```

## 9. 模块 2 已落地文件

```text
apps/api/app/domain/identity.py
apps/api/app/core/security.py
apps/api/app/services/rbac.py
apps/api/app/services/identity_store.py
apps/api/app/schemas/identity.py
apps/api/app/routes/identity.py
apps/api/tests/test_identity_store.py
apps/api/tests/test_identity_api.py
docs/MODULE_02_IDENTITY_RBAC.md
```

## 10. 模块 3 已落地文件

```text
apps/api/app/domain/agent.py
apps/api/app/services/agent_store.py
apps/api/app/schemas/agent.py
apps/api/app/routes/agents.py
apps/api/tests/test_agent_store.py
apps/api/tests/test_agents_api.py
docs/MODULE_03_AGENT_WORKSPACE.md
```

## 11. 模块 4-5 已落地文件

```text
apps/api/app/domain/session.py
apps/api/app/services/session_store.py
apps/api/app/schemas/session.py
apps/api/app/routes/sessions.py
apps/api/app/routes/context.py
apps/api/tests/test_session_store.py
apps/api/tests/test_context_api.py
docs/MODULE_04_SESSION_CONTEXT.md
```

## 12. 模块 6 已落地文件

```text
apps/api/app/domain/skill.py
apps/api/app/services/skill_store.py
apps/api/app/schemas/skill.py
apps/api/app/routes/skills.py
apps/api/tests/test_skill_store.py
docs/MODULE_06_SKILL_REGISTRY.md
```

## 13. 模块 7 已落地文件

```text
apps/api/app/domain/mcp.py
apps/api/app/services/mcp_store.py
apps/api/app/schemas/mcp.py
apps/api/app/routes/mcp.py
apps/api/tests/test_mcp_store.py
docs/MODULE_07_MCP_REGISTRY.md
```

## 14. 模块 8 已落地文件

```text
apps/api/app/domain/workflow.py
apps/api/app/services/workflow_store.py
apps/api/app/schemas/workflow.py
apps/api/app/routes/workflows.py
apps/api/tests/test_workflow_store.py
docs/MODULE_08_WORKFLOW_VERSIONING.md
```

## 15. 模块 9 已落地文件

```text
apps/web/app/workflows/page.tsx
apps/web/features/workflows/WorkflowEditor.tsx
docs/MODULE_09_WORKFLOW_EDITOR.md
```

## 16. 模块 10 已落地文件

```text
apps/api/app/domain/workflow_run.py
apps/api/app/services/workflow_run_store.py
apps/api/app/schemas/workflow_run.py
apps/api/app/routes/workflow_runs.py
apps/api/tests/test_workflow_run_store.py
apps/worker/app/tasks/workflow.py
apps/worker/tests/test_workflow_task.py
packages/workflow/executor.py
docs/MODULE_10_WORKFLOW_EXECUTION.md
```

## 17. 模块 11 已落地文件

```text
apps/api/app/gateway/llm.py
apps/api/app/routes/gateway.py
apps/api/app/schemas/gateway.py
apps/api/tests/test_llm_gateway.py
docs/MODULE_11_GATEWAY_LLM.md
```

## 18. 模块 12 已落地文件

```text
packages/runtime/prompt_compiler.py
apps/api/app/gateway/llm.py
apps/api/tests/test_llm_gateway.py
docs/MODULE_12_PROMPT_COMPILER.md
```

## 19. 模块 13 已落地文件

```text
apps/api/app/gateway/rate_limiter.py
apps/api/tests/test_rate_limiter.py
docs/MODULE_13_RATE_LIMITING.md
```

## 20. 模块 14 已落地文件

```text
apps/api/app/domain/memory.py
apps/api/app/services/memory_store.py
apps/api/app/schemas/memory.py
apps/api/app/routes/memory.py
apps/api/tests/test_memory_store.py
docs/MODULE_14_MEMORY_MANAGER.md
```
