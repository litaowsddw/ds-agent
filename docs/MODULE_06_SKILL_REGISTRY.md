# 模块 6：Skill Registry MVP

## 1. 模块目标

模块 6 实现 OpenClaw 风格的 Skill 组织能力：

- 支持 `SKILL.md` frontmatter 解析。
- 支持组织级、群组级、Agent 级 Skill。
- 支持 Agent Skill allowlist。
- Context 中只注入 Skill 摘要，不注入完整内容。

## 2. 当前实现范围

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/skills` | 注册 Skill |
| PUT | `/skills/agents/{agent_id}/policy` | 设置 Agent Skill 授权 |
| GET | `/skills/agents/{agent_id}/summaries` | 查看 Agent 可用 Skill 摘要 |
| GET | `/skills/agents/{agent_id}/skills/{skill_id}` | 读取已授权 Skill 元信息 |

## 3. SKILL.md 格式

```markdown
---
name: workflow-helper
description: 帮助用户设计和检查工作流。
---

# Instructions

当用户需要设计工作流时使用该 Skill。
```

MVP 阶段解析：

- `name`
- `description`

后续会扩展：

- `metadata`
- `requires`
- `risk`
- `user-invocable`

## 4. 上下文注入原则

Context Engine 当前只注入：

```text
skill_id
name
description
scope
```

完整 `SKILL.md` 只有在 Agent 明确选择 Skill 后才读取，避免上下文膨胀，也保持 Reasonix prefix-cache 友好。

## 5. 测试

测试文件：

```text
apps/api/tests/test_skill_store.py
```

覆盖场景：

- 注册 Skill。
- 授权 Skill 给 Agent。
- Agent 获取可用 Skill 摘要。
- 未授权 Skill 不能读取完整内容。

## 6. 下一步

模块 7：MCP Registry MVP。

计划新增：

- MCP Server 注册。
- transport 类型。
- Tool schema 快照。
- Agent MCP allowlist。
- MCP 调用前权限和限流接口预留。

