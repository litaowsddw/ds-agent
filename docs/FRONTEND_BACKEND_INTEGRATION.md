# 前后端完整联调说明

## 目标

本阶段把 Next.js 工作台与 FastAPI 后端主要 MVP 模块打通，让前端不再只是单一工作流 Demo，而是可以真实调用后端完成完整联调：

- API 健康检查
- 用户、组织、团队、成员和 RBAC 验证
- Agent 创建和 Workspace 文件更新
- Session 创建、消息追加和摘要压缩
- Skill 注册、Agent 授权、摘要读取和全文读取
- MCP Server 注册、Tool 快照写入、Agent 授权和可调用验证
- Memory 写入和关键词召回
- Context Engine 组装 Workspace、消息、Skill 摘要和 Memory
- Gateway Mock LLM 调用和调用日志读取
- Workflow 创建、草稿保存、发布、运行和节点日志读取
- 组织审计日志读取

## 技术栈

- 前端：Next.js、React、TypeScript、Tailwind CSS、React Flow、lucide-react
- 后端：FastAPI、Pydantic、内存态 MVP Store、Workflow Executor、Mock LLM Gateway
- 联调地址：
  - 前端：`http://127.0.0.1:3000/workflows`
  - 后端：`http://127.0.0.1:8000`
  - 健康检查：`http://127.0.0.1:8000/health`

## 页面结构

`apps/web/features/workflows/WorkflowEditor.tsx` 是当前完整联调主页面，分为三个区域：

- 左侧操作区：展示 API 状态、节点组件、一键全链路联调、保存草稿、操作反馈。
- 中间工作区：上半部分是 React Flow 画布，下半部分展示各后端模块联调步骤和状态。
- 右侧详情区：展示节点属性、后端资源 ID、联调指标、Workflow DSL 和完整输出。

桌面端使用三栏布局，移动端切换为纵向布局，避免画布标题、节点组件和详情面板被压缩。

## 联调流程

点击「一键全链路联调」后，前端按顺序调用以下接口：

1. `GET /health`
2. `POST /identity/users/register`
3. `POST /identity/organizations`
4. `POST /identity/organizations/{org_id}/teams`
5. `POST /identity/organizations/{org_id}/members`
6. `POST /agents`
7. `PUT /agents/{agent_id}/workspace/file`
8. `POST /sessions`
9. `POST /sessions/{session_id}/messages`
10. `POST /sessions/{session_id}/compact`
11. `POST /skills`
12. `PUT /skills/agents/{agent_id}/policy`
13. `GET /skills/agents/{agent_id}/summaries`
14. `POST /mcp/servers`
15. `POST /mcp/servers/{server_id}/tools`
16. `PUT /mcp/agents/{agent_id}/policy`
17. `GET /mcp/agents/{agent_id}/tools/{tool_id}/can-call`
18. `POST /memory`
19. `POST /memory/recall`
20. `GET /context/sessions/{session_id}/assemble`
21. `POST /gateway/llm/generate`
22. `GET /gateway/llm/logs`
23. `POST /workflows`
24. `POST /workflows/{workflow_id}/publish`
25. `POST /workflow-runs`
26. `GET /workflow-runs/{run_id}/nodes`
27. `GET /identity/organizations/{org_id}/audit-logs`

## 结果展示

运行成功后，页面会展示：

- 用户、组织、团队、Agent、Session、Skill、MCP Tool、Memory、Workflow、Run 等资源 ID。
- Context section 数量、Node Run 数量、Gateway Log 数量和 Audit Log 数量。
- Workflow Run 状态，成功时应为 `succeeded`。
- 结构化输出，包含 Context 摘要、Workflow 输出、节点运行状态、Gateway 日志数量和审计日志数量。

## 错误处理

前端统一通过 `apiRequest` 调用 API。若后端返回错误：

- 字符串错误会直接展示。
- Pydantic 校验错误数组会提取 `msg` 并拼接展示。
- 对象错误会优先展示 `msg`，否则展示 JSON 字符串。

权限负向验证使用 `apiRequestExpectError`，当前验证 viewer 创建 Agent 会返回 `403`。

## 验证记录

已完成以下验证：

- 后端全量测试：`34 passed`
- 前端生产构建：`next build` 通过
- 新增 API 集成测试：`apps/api/tests/test_full_api_integration.py`
- API 健康检查：`/health` 返回 `{"status":"ok","service":"api"}`
- Browser 桌面验证：页面可加载、无控制台错误、一键全链路联调成功、Run 状态为 `succeeded`
- Browser 移动验证：390px 宽度下页面内容可读，主操作入口可见，无控制台错误

截图保存在仓库外部：

- `D:\LTAgent\test-artifacts\workflows-full-integration-desktop.png`
- `D:\LTAgent\test-artifacts\workflows-full-integration-mobile.png`

## 当前边界

- 当前仍使用 MVP 内存态 Store，页面刷新或 API 重启后测试数据不会持久保存。
- 当前真实执行节点仍以 `Start -> LLM -> End` 为主，RAG 和 Tool 节点在前端可添加，但后端执行器尚未实现真实 RAG/Tool 节点执行。
- 当前异步模式仍依赖本地 Celery 可用性，本轮完整联调默认使用同步 `WorkflowRun` 执行。
- 当前 Mock LLM Provider 不访问外部模型服务，用于本地开发和测试。

## 后续优化

- 接入真实登录态，替换 MVP 阶段显式传入的 `actor_user_id`。
- 把 Workflow、Agent、Run、Skill、MCP、Memory 列表改为持久化数据库读取。
- 增加节点配置表单，支持 LLM、RAG、Tool、Condition 的差异化配置。
- 增加运行历史列表、节点级日志、Gateway 调用日志和限流命中展示。
- 增加 Playwright E2E 自动化测试，固化浏览器联调场景。
