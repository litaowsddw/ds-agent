# 前后端联调说明

## 目标

本阶段把 Next.js 工作流编辑器与 FastAPI 后端主链路打通，让前端不再只是静态画布，而是可以真实调用后端完成：

- API 健康检查
- 测试用户注册
- 组织创建
- Agent 创建
- Workflow 草稿保存
- Workflow 版本发布
- Workflow Run 同步执行
- 运行结果回显

## 技术栈

- 前端：Next.js、React、TypeScript、Tailwind CSS、React Flow、lucide-react
- 后端：FastAPI、Pydantic、内存态 MVP Store、Workflow Executor、Mock LLM Gateway
- 联调地址：
  - 前端：`http://127.0.0.1:3000/workflows`
  - 后端：`http://127.0.0.1:8000`
  - 健康检查：`http://127.0.0.1:8000/health`

## 页面结构

`apps/web/features/workflows/WorkflowEditor.tsx` 是当前联调主页面，分为三个区域：

- 左侧操作区：展示 API 状态、节点组件、一键联调运行、保存草稿、操作反馈。
- 中间画布区：使用 React Flow 展示并编辑 Workflow 节点与连线。
- 右侧详情区：展示节点属性、后端返回的用户/组织/Agent/Workflow/Run 信息、DSL 和运行输出。

桌面端使用三栏布局，移动端自动切换为纵向布局，避免画布标题和面板内容被压缩。

## 联调流程

点击「一键联调运行」后，前端按顺序调用以下接口：

1. `POST /identity/users/register`
2. `POST /identity/organizations`
3. `POST /agents`
4. `POST /workflows`
5. `POST /workflows/{workflow_id}/publish`
6. `POST /workflow-runs`

运行成功后，页面会展示：

- `user_id`
- `org_id`
- `agent_id`
- `workflow_id`
- `version_id`
- `run_id`
- `status`
- `output_data`

## 错误处理

前端统一通过 `apiRequest` 方法调用 API。若后端返回错误：

- 字符串错误会直接展示。
- Pydantic 校验错误数组会提取 `msg` 并拼接展示。
- 对象错误会优先展示 `msg`，否则展示 JSON 字符串。

这样可以避免页面出现 `[object Object]` 这类不可读提示。

## 验证记录

已完成以下验证：

- 后端全量测试：`33 passed`
- 前端生产构建：`next build` 通过
- API 健康检查：`/health` 返回 `{"status":"ok","service":"api"}`
- Browser 桌面验证：页面可加载、无控制台错误、一键联调成功、Run 状态为 `succeeded`
- Browser 移动验证：390px 宽度下页面内容可读，主操作入口可见，无控制台错误

截图保存在仓库外部：

- `D:\LTAgent\test-artifacts\workflows-integration-desktop.png`
- `D:\LTAgent\test-artifacts\workflows-mobile.png`

## 后续优化

- 接入真实登录态，替换 MVP 阶段显式传入的 `actor_user_id`。
- 把 Workflow、Agent、Run 列表改为持久化数据库读取。
- 增加节点配置表单，支持 LLM、RAG、Tool、Condition 的差异化配置。
- 增加运行历史列表、节点级日志、Gateway 调用日志和限流命中展示。
- 增加前端自动化端到端测试。
