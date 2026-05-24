# 模块 4-5：Session Manager 与 Context Engine

## 1. 模块目标

本阶段把 OpenClaw 风格的长期 Agent 会话能力接入系统：

- Agent Session。
- Append-only 消息存储。
- queue / collect 消息模式。
- Session 与 Agent/Org 隔离。
- Context Engine 从 Workspace 和 Session 组装上下文。

## 2. 当前实现范围

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/sessions` | 创建 Agent Session |
| GET | `/sessions/{session_id}` | 读取 Session |
| POST | `/sessions/{session_id}/messages` | 追加消息 |
| GET | `/sessions/{session_id}/messages` | 列出消息 |
| POST | `/sessions/{session_id}/compact` | 写入压缩摘要 |
| GET | `/context/sessions/{session_id}/assemble` | 组装 Session 上下文 |

## 3. Session 设计

Session 绑定：

```text
org_id
agent_id
user_id
queue_mode
status
compact_summary
```

消息采用 append-only：

```text
message_id
session_id
role
content
sequence
estimated_tokens
compacted
```

原则：

- 消息只追加，不插入、不重排。
- 压缩历史只写摘要，不删除原文。
- 跨组织用户不能读取 Session。
- Context Engine 接收轻量结构，避免依赖 API 领域模型。

## 4. Context Engine 分层

当前上下文分为：

| 层 | 来源 |
| --- | --- |
| workspace | `AGENTS.md`、`SOUL.md`、`TOOLS.md`、`MEMORY.md` |
| compact_summary | Session 压缩摘要 |
| append_only_messages | Session 消息历史 |
| current_input | 当前回合输入 |

该顺序符合 Reasonix 风格的 prefix-cache 友好设计：稳定 Workspace 前置，动态输入后置。

## 5. 测试

测试文件：

```text
apps/api/tests/test_session_store.py
apps/api/tests/test_context_api.py
```

覆盖场景：

- Session 消息按 append-only 顺序保存。
- 跨组织用户不能读取 Session。
- 压缩 Session 后消息标记为 compacted。
- Context API 可以从 Workspace 和 Session 组装上下文。

## 6. 下一步

继续开发模块 6：Skill Registry MVP。

计划新增：

- `SKILL.md` 解析。
- bundled/org/team/agent 多层 Skill。
- Agent Skill allowlist。
- Context 中只注入 Skill 摘要。

