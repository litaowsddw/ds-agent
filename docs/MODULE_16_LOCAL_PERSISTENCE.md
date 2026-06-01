# Module 16：本地持久化 MVP

## 目标

让 AgentFlow Studio 从“演示态”进入“可反复使用”的 MVP：用户创建的组织、Agent、Workspace、模型供应商、Skill、MCP、Memory、Session、Workflow 和运行记录在 API 重启后不丢失。

## 实现范围

新增本地状态文件：

```text
.agentflow/state.pkl
```

默认启用：

```env
AGENTFLOW_PERSISTENCE=1
AGENTFLOW_STATE_FILE=.agentflow/state.pkl
```

测试环境通过 `apps/api/tests/conftest.py` 关闭持久化，确保自动化测试仍然使用干净内存状态。

## 已持久化资源

- 用户、组织、团队、成员关系、审计日志
- Agent 与 Agent Workspace
- Session 与 append-only messages
- Skill 与 Agent Skill 授权策略
- MCP Server、MCP Tool 与 Agent MCP 授权策略
- Memory
- 模型供应商配置
- Workflow 草稿与发布版本
- Workflow Run 与 Node Run

## 设计说明

当前本地持久化使用 Python `pickle` 保存 Store bucket。这样可以最小改动地保留现有领域模型、枚举、时间字段和服务接口，适合 MVP 本地使用。

重要边界：

- 该文件只适合本地开发和单机 MVP。
- 不应把 `.agentflow/` 提交到 GitHub。
- 不应把不可信来源的 `state.pkl` 放入运行环境。
- 生产版本应替换为 PostgreSQL + 加密字段 + Alembic 迁移。

## 验收方式

1. 启动 API。
2. 创建用户、组织、Agent、模型供应商、Workflow。
3. 发布并运行 Workflow。
4. 重启 API。
5. 再次读取 Agent、模型供应商、Workflow、Run、Node Run。

本轮本地验收结果：

```json
{
  "agent_count": 1,
  "provider_count": 1,
  "workflow_count": 1,
  "run_count": 1,
  "node_count": 3,
  "run_status": "succeeded"
}
```

## 后续升级

- 用 PostgreSQL 替换本地状态文件。
- API Key 改为加密存储。
- 增加备份、恢复和数据迁移命令。
- 增加组织级数据导入导出。
