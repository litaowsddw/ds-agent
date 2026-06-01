# AgentFlow 开发规范

## 1. 代码可读性

- 函数只做一件事。
- 模块边界清晰。
- 命名必须表达业务含义。
- 避免过早抽象。
- 不把网关、运行时、工作流执行逻辑混在同一个函数中。

## 2. 中文注释规范

所有新增核心代码必须使用中文注释。

推荐注释粒度：

- 模块顶部说明模块职责。
- 类说明业务角色。
- 函数说明输入、输出、副作用。
- 复杂变量说明业务含义。
- 状态机、权限、限流、缓存逻辑必须写清判断理由。

简单变量不需要机械注释，例如 `name`、`id`、`count`。但领域变量需要注释，例如 `tenant_scope`、`prefix_hash`、`token_budget`。

## 3. 文档同步要求

每完成一个模块，必须更新：

- `docs/PROJECT_STRUCTURE.md`
- 对应模块文档
- README 中的当前阶段说明

## 4. 测试要求

每个模块必须有独立测试：

- 后端模块使用 pytest。
- 前端模块使用 Vitest。
- 工作流主链路使用 Playwright。
- 异步任务使用 Celery 集成测试。

## 5. Git 规范

提交信息建议：

```text
feat(api): 添加用户组织模型
feat(runtime): 添加 ContextEngine MVP
test(worker): 添加 Celery smoke 测试
docs(plan): 更新开发计划
```

