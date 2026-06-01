# AgentFlow Studio 前后端对接说明

## 目标

本阶段不再把前端定位为“接口测试页面”，而是搭建一个面向用户的 Agent Studio MVP。用户可以从空工作空间开始，创建 Agent、配置运行时能力、搭建 Workflow、发布运行并查看结果。

当前仍然是 MVP 内存态实现，但前端交互已经按真实产品工作流组织，而不是按接口测试脚本组织。

## 用户可用能力

`apps/web/features/workflows/WorkflowEditor.tsx` 提供以下用户侧工作台：

- 工作空间创建：创建本地用户、组织和团队。
- Agent 管理：创建 Agent、选择 Agent、编辑 `AGENTS.md` Workspace 指令。
- Workflow 编辑：React Flow 画布、节点添加、草稿保存、版本发布、同步运行。
- Runtime 配置：创建并授权 Skill、MCP Server/Tool、Memory。
- Session/Context：创建 Session、追加消息、组装 Context。
- Gateway：调用 Mock LLM Provider，并查看 Gateway 调用日志。
- Runs：查看 Workflow Run 历史、输出结果、Node Run 日志和发布版本。

## 后端服务接口

为了支撑 Studio 的真实查询和管理能力，本阶段新增或补齐了以下列表接口：

- `GET /workflows`
- `GET /workflow-runs`
- `GET /sessions`
- `GET /memory`
- `GET /skills`
- `GET /mcp/servers`

这些接口补齐了真实应用必需的资源列表、运行历史和能力配置查询，避免前端只能靠一键测试流程持有临时状态。

## 核心用户流程

1. 用户进入 `http://127.0.0.1:3000/workflows`。
2. 创建工作空间，后端生成用户、组织和团队。
3. 创建 Agent，后端初始化 Agent Workspace。
4. 编辑并保存 `AGENTS.md`。
5. 创建 Skill、MCP Tool、Memory，并绑定到 Agent。
6. 创建 Session 并组装 Context。
7. 在 Workflow 画布中编辑节点和连线。
8. 创建 Workflow，保存草稿，发布版本。
9. 输入运行文本并执行 Workflow。
10. 在 Runs 页面查看运行历史、节点日志和输出结果。

## 测试覆盖

新增后端测试：

- `apps/api/tests/test_full_api_integration.py`

该测试覆盖 Studio 依赖的主要接口：

- Identity / Organization / Team / Member
- Agent / Workspace
- Session / Message / Compact
- Skill / Policy / Summaries
- MCP Server / Tool / Policy
- Memory / Recall / List
- Context Assemble
- Gateway Generate / Logs
- Workflow Create / List / Publish
- Workflow Run / List / Node Runs
- RBAC 负向验证
- Audit Logs

## 当前边界

- 数据仍保存在进程内存中，刷新后前端状态会保留但 API 重启后资源会消失。
- RAG 和 Tool 节点目前是 Studio 可添加节点，但后端执行器真实执行仍只支持 `start`、`llm`、`end`。
- 当前登录态仍是 MVP 显式 `actor_user_id`，后续要替换为认证中间件。
- 当前 Mock LLM Provider 不访问外部模型，用于本地开发、测试和演示。

## 验证命令

```powershell
python -m pytest -q
cd apps/web
npm run build
```

Browser 验证应覆盖：

- 创建工作空间
- 创建 Agent
- 创建 Skill / MCP / Memory
- 创建 Session 并组装 Context
- 创建、发布并运行 Workflow
- Runs 页面显示运行结果和节点日志
