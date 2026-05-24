# 当前开发状态

## 已完成

- 完整中文开发计划：`docs/DEVELOPMENT_PLAN.md`
- 项目结构文档：`docs/PROJECT_STRUCTURE.md`
- 开发规范：`docs/DEVELOPMENT_GUIDE.md`
- 模块 1 文档：`docs/MODULE_01_FOUNDATION.md`
- 模块 2 文档：`docs/MODULE_02_IDENTITY_RBAC.md`
- API 服务骨架：`apps/api`
- Worker 服务骨架：`apps/worker`
- 前端工作台骨架：`apps/web`
- Runtime 抽象：`packages/runtime`
- Workflow 抽象：`packages/workflow`
- Docker Compose：`docker-compose.yml`
- GitHub Actions：`.github/workflows/ci.yml`
- 用户、组织、群组、RBAC、审计日志 MVP：`apps/api/app/services/identity_store.py`
- Agent 与 Workspace MVP：`apps/api/app/services/agent_store.py`
- Session 与 Context Engine MVP：`apps/api/app/services/session_store.py`
- Skill Registry MVP：`apps/api/app/services/skill_store.py`
- MCP Registry MVP：`apps/api/app/services/mcp_store.py`
- Workflow DSL 与版本管理 MVP：`apps/api/app/services/workflow_store.py`
- 前端 Workflow Editor MVP：`apps/web/features/workflows/WorkflowEditor.tsx`
- Workflow 执行引擎 MVP：`packages/workflow/executor.py`
- Gateway + LLM Provider MVP：`apps/api/app/gateway/llm.py`
- Prompt Compiler + prefix hash MVP：`packages/runtime/prompt_compiler.py`

## 已验证

- Python 语法已通过 AST 检查。
- Workflow 执行主链路已通过手动校验。

## 当前环境限制

- 当前 Python 环境缺少 `pytest`，所以本机未能运行完整测试套件。
- 当前 Python 环境缺少 `celery`，Worker 任务函数通过 LocalCelery fallback 完成本地校验。
- 当前 Windows 工作区对 `.git` 目录存在 ACL 写入限制，`git init` 未能完成。
- 当前 Windows 工作区对 `__pycache__` 写入/重命名存在权限限制，已改用不写 pyc 的语法检查方式。

## 下一步

模块 13：全局限流与并发控制。

计划新增：

- Redis token bucket 抽象。
- 本地 fallback 限流器。
- provider/model/org/agent 多维限流 key。
- Gateway 调用前限流检查。
