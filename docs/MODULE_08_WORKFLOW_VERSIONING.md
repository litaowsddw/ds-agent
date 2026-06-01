# 模块 8：Workflow DSL 与版本管理增强

## 1. 模块目标

模块 8 将工作流从静态 DSL 升级为可管理资源：

- Workflow 草稿。
- Workflow 发布版本。
- 发布版本不可变。
- DAG 环检测。
- Start -> LLM -> End 的发布校验。

## 2. 当前实现范围

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/workflows` | 创建 Workflow 草稿 |
| GET | `/workflows/{workflow_id}` | 读取 Workflow |
| PUT | `/workflows/{workflow_id}/draft` | 更新草稿 |
| POST | `/workflows/{workflow_id}/publish` | 发布版本 |
| GET | `/workflows/{workflow_id}/versions` | 列出版本 |

## 3. DSL 校验

当前校验规则：

- 节点 ID 不能重复。
- 必须包含 `start` 节点。
- 必须包含 `end` 节点。
- 连线起点和终点必须存在。
- DAG 不能包含环。

## 4. 版本不可变

发布时会深拷贝草稿 DSL 到 `WorkflowVersion.definition`。
后续更新草稿不会修改已经发布的版本。

## 5. 测试

测试文件：

```text
apps/api/tests/test_workflow_store.py
packages/workflow/tests/test_validator.py
```

## 6. 下一步

模块 9：前端可视化工作流编辑器增强。

