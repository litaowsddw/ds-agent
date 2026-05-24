# 模块 9：前端可视化工作流编辑器增强

## 1. 模块目标

模块 9 提供 Dify 风格工作流编辑体验的 MVP 骨架：

- React Flow 画布。
- Start / LLM / End 默认节点。
- 节点连线。
- 添加 LLM 节点。
- 节点属性面板。
- 草稿 DSL 预览。

## 2. 当前实现范围

页面：

```text
apps/web/app/workflows/page.tsx
```

核心组件：

```text
apps/web/features/workflows/WorkflowEditor.tsx
```

## 3. 当前交互

- 打开 `/workflows` 可看到默认 `Start -> LLM -> End` 工作流。
- 可拖动画布节点。
- 可连接节点。
- 可新增 LLM 节点。
- 点击节点后右侧显示节点属性。
- 右侧展示当前画布生成的 Workflow DSL。

## 4. 后续接入

下一步会把“保存草稿”和“发布版本”按钮接入后端：

- `POST /workflows`
- `PUT /workflows/{workflow_id}/draft`
- `POST /workflows/{workflow_id}/publish`

## 5. 测试计划

后续安装前端依赖后执行：

```bash
cd apps/web
npm install
npm run build
```

再加入 Playwright E2E：

- 打开 `/workflows`。
- 添加 LLM 节点。
- 连线。
- 检查 DSL JSON 更新。

