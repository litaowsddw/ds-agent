---
name: workflow-builder
description: 创建、校验和解释 AgentFlow 可视化工作流；当用户要求搭建、修改或排查 Workflow 时使用。
---

# Workflow Builder

帮助用户在 AgentFlow 中设计和维护可视化工作流。

## 步骤

1. 明确业务目标：输入是什么、期望输出是什么、中间需要哪些处理步骤。
2. 选择节点类型：LLM（模型调用）、Knowledge Retrieval（知识库检索）、Tool（授权工具）、Condition（条件分支）。
3. 保持图是一个从 Start 到 End 的 DAG；Condition 节点必须同时连接 true 和 false 两条分支。
4. 为每个节点补齐必要配置：LLM 需要 provider/model，检索需要知识库，工具需要授权工具 ID。
5. 发布前先运行检查（checklist），确认没有未配置节点和不可达节点。

## 注意事项

- 不要在 LLM 节点的 prompt 里依赖花括号插值；上游输出通过运行时上下文传递。
- 引用上游结果使用 `{{upstream.<node_id>.<field>}}` 或 `{{input.<field>}}` 格式。
- 高风险工具调用需要人工审批，不要绕过审批路径。
