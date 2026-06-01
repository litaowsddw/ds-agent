# 模块 7：MCP Registry MVP

## 1. 模块目标

模块 7 实现 MCP 服务注册和 Agent 授权边界：

- MCP Server 注册。
- MCP Tool schema 快照。
- Agent MCP allowlist。
- MCP Tool 调用前权限校验。
- 为后续真实 MCP Client 调用、限流、审计预留接口。

## 2. 当前实现范围

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/mcp/servers` | 注册 MCP Server |
| POST | `/mcp/servers/{server_id}/tools` | 写入 MCP Tool 快照 |
| PUT | `/mcp/agents/{agent_id}/policy` | 设置 Agent MCP 授权 |
| GET | `/mcp/agents/{agent_id}/tools` | 列出 Agent 可用 MCP Tool |
| GET | `/mcp/agents/{agent_id}/tools/{tool_id}/can-call` | 校验工具调用权限 |

## 3. Transport

MVP 支持声明：

- `http`
- `sse`
- `streamable_http`

`stdio` 暂不纳入 MVP，因为多租户服务端环境需要额外 sandbox 和进程隔离。

## 4. 安全规则

- MCP Server 必须归属组织。
- Agent 只能使用同组织 MCP Server。
- Agent 必须显式授权后才能看到 MCP Tool。
- Tool 调用前必须经过 `assert_agent_can_call_tool`。
- 真实调用后续必须经过 Gateway 的限流、审计和缓存。

## 5. 测试

测试文件：

```text
apps/api/tests/test_mcp_store.py
```

覆盖场景：

- Agent 被授权后可以看到 MCP Tool。
- 未授权 MCP Tool 调用会被拒绝。

## 6. 下一步

模块 8：Workflow DSL 与版本管理增强。

计划新增：

- Workflow draft。
- Workflow version。
- 发布版本不可变。
- DAG 环检测。
- Start -> LLM -> End 的发布校验。

