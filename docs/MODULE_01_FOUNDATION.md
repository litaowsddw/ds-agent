# 模块 1：项目骨架与基础设施

## 1. 模块目标

模块 1 的目标是建立 AgentFlow 的最小可运行骨架：

- API 服务入口。
- Worker 服务入口。
- Runtime 抽象。
- Workflow DSL 抽象。
- 前端工作台入口。
- Docker Compose 基础设施。
- 中文开发文档。

## 2. 当前目录

```text
apps/api
  FastAPI 服务

apps/worker
  Celery Worker 服务

apps/web
  Next.js 前端工作台

packages/runtime
  Agent Runtime、Context、Skill、MCP、Memory、Prompt Compiler

packages/workflow
  Workflow DSL 和校验器
```

## 3. 已实现能力

### 3.1 API

- `/health`：健康检查。
- `/runtime/describe`：查看 Runtime 能力。
- `/runtime/context/assemble`：组装最小上下文。
- `/runtime/prompt/compile`：编译 prefix-cache 友好 Prompt。

### 3.2 Worker

- `agentflow.smoke.ping`：Worker 冒烟任务。
- `agentflow.background.memory_compact`：后台记忆压缩任务入口。
- `agentflow.background.mcp_health_check`：MCP 健康检查任务入口。

### 3.3 Runtime

- `AgentRuntime`：Agent 运行时边界。
- `ContextEngine`：上下文生命周期。
- `PromptContextCompiler`：稳定 Prompt 编译和 prefix hash。
- `SkillRegistry`：Skill 摘要注册表。
- `MCPRegistry`：MCP Server 注册表。
- `MemoryManager`：内存管理接口。

### 3.4 Workflow

- `WorkflowDefinition`：工作流定义。
- `WorkflowNode`：工作流节点。
- `WorkflowEdge`：工作流边。
- `WorkflowValidator`：基础校验器。

## 4. 测试方式

后端基础测试：

```bash
pytest
```

前端本地启动：

```bash
cd apps/web
npm install
npm run dev
```

Docker Compose 启动：

```bash
docker compose up --build
```

## 5. 下一步

模块 2 将实现用户、组织、群组和权限隔离，并把当前调试接口接入真实租户边界。

