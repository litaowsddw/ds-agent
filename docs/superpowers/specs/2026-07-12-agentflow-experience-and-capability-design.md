# AgentFlow 界面体验与实用功能双轨优化设计

## 目标

本轮优化围绕一条完整用户路径展开：用户选择工作空间和 Agent，跨页面保持一致上下文，在不同设备上顺畅操作，通过 Chat 发起任务，并在 Runs 中快速理解执行结果与失败原因。

成功标准：

- Agent 选择在全局可见、可切换，跨页面不会出现上下文漂移。
- 桌面端维持现有信息密度，窄屏下导航和核心页面仍可操作。
- Runs 默认展示可读信息，原始 JSON 作为二级详情保留。
- Chat 主要交互统一为中文，执行轨迹可完整查看，回答可复制。
- 每项功能拥有独立测试、独立 Git commit，可单独回滚。

## 范围与非目标

本轮包含四个独立增量：全局 Agent 上下文、响应式应用框架、Runs 可观测性、Chat 交互完善。

本轮不重做视觉品牌，不更改后端执行协议，不引入新的 UI 框架，不重构与四项增量无关的页面。大文件只在实现相应功能时提取必要子组件。

## 1. 全局 Agent 上下文

### 组件与职责

- `Header` 承载工作空间摘要和 Agent 选择器；无 Agent 时提供前往 Agents 页的明确入口。
- 新建独立 `AgentContextSelector`，只负责展示列表、选择 Agent、加载态和空态，不直接请求业务数据。
- `workspace` store 继续作为 Agent 上下文唯一来源。切换 Agent 时沿用现有 `setSelectedAgentId`，并清理与旧 Agent 绑定的运行选择。
- Chat 移除重复的本地 Agent 下拉，读取同一全局状态。

### 数据流与异常处理

工作空间恢复后刷新 Agent 列表；若持久化的 `selectedAgentId` 不在最新列表中，则清空选择，不自动切换到其他 Agent。空列表与请求失败分别显示“创建 Agent”和轻量错误提示。切换工作空间时清空 Agent、Workflow 和 Run 上下文。

### 测试

- 选择器正确显示 Agent、空态和当前选择。
- 切换 Agent 会清除旧 Run 选择。
- 已删除或跨工作空间的持久化 Agent ID 不再被使用。
- Chat、Workflows、Runs 读取同一 Agent 上下文。
- 当前前端没有组件测试基础设施，因此该功能提交同时引入最小 Vitest 与 Testing Library 配置，并用首批测试验证上述行为。

## 2. 响应式应用框架

### 组件与职责

- `AppLayout` 管理移动端侧边栏开关和遮罩层。
- `Sidebar` 支持桌面常驻、窄屏抽屉两种呈现；路由切换后自动关闭抽屉。
- `Header` 在窄屏展示菜单按钮，并让工作空间、Agent 选择和操作按钮按优先级收缩。
- 页面主区域采用断点间距；Workflow 的工具区与详情区在窄屏使用可切换面板或抽屉，画布保持最大可用面积。

### 行为与可访问性

抽屉支持 Escape 关闭、遮罩关闭、焦点可见和 `aria` 标签。布局避免横向页面级溢出；需要横向空间的表格或代码块在自身容器内滚动。React Flow 容器尺寸变化后触发正常重算，不改变工作流数据。

### 测试

- 桌面端和窄屏端的导航显隐、菜单开关和路由关闭行为。
- Header 核心控件在常见断点可访问。
- 前端构建与类型检查通过；关键页面进行桌面与移动视口冒烟检查。

## 3. Runs 可观测性

### 组件与职责

- 运行列表增加状态筛选、状态徽标、开始时间、耗时、Workflow 名称或标识、失败摘要。
- 运行详情先显示结构化摘要，再提供可折叠原始 JSON。
- 节点日志使用一致的状态徽标和耗时格式；错误信息优先于输出展示。
- 提取 `RunStatusBadge`、`RunSummary` 和 `JsonDisclosure` 等局部组件，避免继续扩大页面文件。

### 数据与降级

优先使用现有领域模型中的真实 `created_at`、`updated_at` 和节点耗时；API schema 与前端类型若尚未暴露这些字段，则在同一功能 commit 中补齐契约和定向 API 测试。缺失时间、耗时或 Workflow 信息时显示短横线，不伪造数据。状态筛选在前端对当前 Agent 的运行集合执行。复制操作失败时显示 Toast；无匹配结果时提供清除筛选入口。

### 测试

- 状态映射、耗时格式化和缺失字段降级。
- 筛选结果、空结果和切换 Agent 后的选择清理。
- 结构化摘要与原始 JSON 折叠均可访问。

## 4. Chat 交互完善

### 组件与职责

- 页面标题、标签、按钮、输入提示和空态统一为中文；保留 Agent、Workflow、Skill 等项目术语。
- 消息显示时间；助手消息提供复制按钮，复制结果通过 Toast 反馈。
- `ThinkingTrace` 默认展示最近事件，提供展开/收起以查看完整轨迹，不再永久截断历史。
- 发送失败保留原始提示词、执行模式和 Workflow 快照，并提供显式重试；切换 Agent 时先清理旧会话可见状态，避免短暂串屏。
- 保留现有自主模式与流程模式，不改变请求载荷和流式协议。

### 错误处理

发送失败保持用户输入或提供可重试路径，不制造重复消息。Clipboard API 不可用或被拒绝时显示失败提示。轨迹为空、进行中、成功和失败均有明确状态。

### 测试

- 中文文案和空态渲染。
- 轨迹默认折叠、展开、运行中状态和错误状态。
- 消息复制成功与失败反馈。
- 自主模式、Workflow 模式和流式消息既有行为回归。

## Git 与交付策略

每个增量遵循“先测试或定义验收点，再实现，再验证，再提交”的闭环。计划 commit 顺序：

1. `docs: design agentflow experience and capability improvements`
2. `feat: add global agent context selector`
3. `feat: make application shell responsive`
4. `feat: improve workflow run observability`
5. `feat: polish chat interaction experience`
6. 必要时单独提交 `chore: add deployment configuration` 和部署文档。

任何功能若需要后端契约变更，后端契约和对应测试应作为该功能 commit 的一部分；无关格式化、重构或依赖升级不得混入。每个 commit 完成后推送到 `feat/agent-default-workflow`。

## 验证与部署

逐功能运行相关前端测试或静态检查；最终运行前端类型检查与生产构建、相关后端测试，并对首页、Agents、Chat、Workflows、Runs 做浏览器冒烟检查。部署使用仓库可支持的容器或托管配置，环境变量和密钥只通过部署环境注入，不写入 Git。部署完成后验证公开 URL、API 健康检查和关键用户路径，再提供访问链接。
