# 模块 10：Celery 工作流执行引擎

## 1. 模块目标

模块 10 将已发布 Workflow Version 变成可运行对象：

- Workflow Run。
- Node Run。
- Start -> LLM -> End 执行链路。
- 运行状态机。
- 节点日志。
- Celery 任务入口。

## 2. 当前实现范围

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/workflow-runs` | 创建 Workflow Run |
| GET | `/workflow-runs/{run_id}` | 查询 Workflow Run |
| GET | `/workflow-runs/{run_id}/nodes` | 查询节点运行日志 |

`POST /workflow-runs` 支持：

- `async_mode=false`：API 进程内同步执行，用于 MVP 调试和测试。
- `async_mode=true`：投递 Celery 任务，并记录 `celery_task_id`。

## 3. 执行器设计

纯执行器位于：

```text
packages/workflow/executor.py
```

它只负责：

- 拓扑排序。
- 节点输入构建。
- 节点执行。
- 输出汇总。

不直接依赖：

- FastAPI。
- 数据库。
- Celery。
- LLM Provider。

## 4. 当前节点支持

| 节点 | 行为 |
| --- | --- |
| start | 输出本次运行输入 |
| llm | 返回 mock LLM 文本，模块 11 替换为 Gateway 调用 |
| end | 汇总上游输出 |

## 5. 状态机

Workflow Run：

```text
pending -> running -> succeeded
pending -> running -> failed
```

Node Run：

```text
pending -> running -> succeeded
pending -> running -> failed
```

MVP 当前同步执行时会直接记录最终节点状态。

## 6. 测试

测试文件：

```text
apps/api/tests/test_workflow_run_store.py
apps/worker/tests/test_workflow_task.py
```

覆盖场景：

- Start -> LLM -> End 可以执行成功。
- 生成 3 条 Node Run。
- Celery task 函数可直接执行 DSL。

## 7. 当前限制

- API 和 Worker 当前仍使用进程内存储，异步任务结果不会自动回写 API 进程内 RunStore。
- 模块 11 接入 Gateway 后，LLM 节点会替换 mock 输出。
- 数据库持久化模块完成后，API 和 Worker 将共享运行状态。
- 当前本地环境缺少 Celery 依赖时，`apps/worker/app/celery_app.py` 会启用 LocalCelery fallback，
  仅用于直接调用任务函数和本地校验；生产环境安装 Celery 后会使用真实 Celery。

## 8. 下一步

模块 11：Gateway + LLM Provider。

计划新增：

- OpenAI-compatible Provider Adapter。
- Gateway 调用日志。
- Provider 错误标准化。
- LLM 节点从 mock 改为 Gateway 调用接口。
