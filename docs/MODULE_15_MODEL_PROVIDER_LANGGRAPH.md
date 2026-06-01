# Module 15：模型供应商与 LangGraph DAG 执行

## 目标

本模块把模型供应商 API 配置从代码中抽离为组织级资源，并把 Workflow 后端执行从手写拓扑遍历升级为 LangGraph DAG 编译执行。前端画布节点直接对应 LangGraph 节点，画布连线直接对应 LangGraph 边。

## 后端能力

- `POST /model-providers`：创建或更新组织级模型供应商配置。
- `GET /model-providers`：列出组织可用模型供应商。
- `POST /gateway/llm/generate`：支持携带 `actor_user_id` 和 `org_id`，按组织解析模型供应商。
- `packages/workflow/executor.py`：使用 LangGraph `StateGraph` 编译 Workflow DSL。

## 支持的供应商形态

当前实现采用 OpenAI-compatible 接口，用户可以配置：

- `provider_key`：供应商 key，例如 `openai`、`deepseek`、`qwen`。
- `display_name`：前端展示名称。
- `base_url`：供应商 API 根地址。
- `api_key`：后端保存的密钥，接口响应只返回掩码。
- `models`：该供应商可选模型列表。
- `default_model`：默认模型。

## LangGraph 映射规则

- Workflow DSL `nodes[]` 映射为 LangGraph node。
- Workflow DSL `edges[]` 映射为 LangGraph edge。
- 无入边节点连接 `START`。
- 无出边节点连接 `END`。
- `start` 节点输出原始输入。
- `llm` 节点通过统一 Gateway 调用模型供应商。
- `rag` 与 `tool` 节点已进入 LangGraph DAG，本阶段先提供安全占位输出，后续接真实 RAG 和 MCP Tool 执行器。
- `end` 节点聚合上游输出作为最终结果。

## 前端能力

- Runtime 页面新增模型供应商配置表单。
- Workflow 页面新增 LLM 节点模型选择：
  - 供应商选择
  - 模型选择
  - 系统提示词
  - 节点提示词
  - temperature
- 保存草稿和发布时，LLM 节点配置会写入 Workflow DSL。

## 测试

- 后端：`python -m pytest -q`
- 前端：`npm run build`
- 集成测试覆盖：
  - 创建模型供应商
  - 查询模型供应商列表
  - Gateway 携带组织上下文调用
  - Workflow Run 经 LangGraph 执行 `start -> llm -> end`

## MVP 边界

- API Key 当前仍为内存态保存，后续需要接入数据库加密字段或 KMS。
- 真实供应商调用已具备 OpenAI-compatible HTTP 适配器，但自动化测试仍使用 Mock Provider，避免依赖外部网络和真实密钥。
- RAG 与 Tool 节点已进入 DAG，但真实检索和工具副作用执行将在后续模块补齐。
