# 模块 3：Agent 管理与 Workspace

## 1. 模块目标

模块 3 让 Agent 成为组织隔离下的真实运行主体：

- Agent 绑定组织。
- Agent 可选绑定群组。
- Agent 创建接入 RBAC。
- Agent 拥有独立 Workspace。
- Workspace 提供 OpenClaw 风格的提示词文件。

## 2. 当前实现范围

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/agents` | 创建 Agent |
| GET | `/agents` | 按组织列出 Agent |
| GET | `/agents/{agent_id}` | 读取 Agent |
| GET | `/agents/{agent_id}/workspace` | 读取 Agent Workspace |
| PUT | `/agents/{agent_id}/workspace/file` | 更新 Workspace 文件 |

## 3. Workspace 文件

MVP 默认初始化四个文件：

| 文件 | 说明 |
| --- | --- |
| `AGENTS.md` | 定义 Agent 的角色、目标和长期约束 |
| `SOUL.md` | 定义 Agent 的表达风格、偏好和协作方式 |
| `TOOLS.md` | 记录 Agent 可用工具、MCP 服务和调用边界 |
| `MEMORY.md` | 记录 Agent 的长期记忆摘要和人工确认事实 |

## 4. 权限规则

- 创建 Agent 需要 `agent:create` 权限。
- 更新 Workspace 文件需要 `agent:create` 权限。
- 读取 Agent 和 Workspace 需要 `organization:read` 权限。
- 任何跨组织读取都会返回 403。
- 如果绑定 `team_id`，群组必须属于同一个组织。

## 5. 核心目录

```text
apps/api/app/domain/agent.py
  Agent 和 AgentWorkspace 领域模型

apps/api/app/services/agent_store.py
  Agent 与 Workspace MVP 存储

apps/api/app/schemas/agent.py
  Agent API 请求和响应模型

apps/api/app/routes/agents.py
  Agent API 路由
```

## 6. 测试

测试文件：

```text
apps/api/tests/test_agent_store.py
apps/api/tests/test_agents_api.py
```

覆盖场景：

- developer 可以创建 Agent。
- viewer 不能创建 Agent。
- Workspace 文件可以被有权限用户更新。
- API 可以创建 Agent 并读取 Workspace。
- 其他组织用户不能读取 Agent Workspace。

## 7. 下一步

模块 4 将实现 Session Manager 与消息存储：

- Agent Session。
- Append-only 消息表。
- queue / collect 模式。
- 为 Context Engine 提供真实会话历史。

