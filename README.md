# AgentFlow

AgentFlow 是一个开源 Agent 工作流框架，目标是提供类似 Dify 的可视化工作流搭建体验，并在后端提供参考 OpenClaw 思路的 Agent Runtime、上下文管理、MCP 服务、Skill 组织、内存管理、后台 Agent 服务、网关、异步任务调度、限流和缓存体系。

## 当前阶段

当前仓库处于 `v0.1` 起步阶段，优先完成：

1. 项目骨架与基础设施。
2. FastAPI API 服务。
3. Celery + Redis Worker 服务。
4. Next.js 前端工作台。
5. Agent Runtime 核心抽象。
6. 中文开发计划与项目结构文档。

## 技术栈

- 前端：Next.js、React、TypeScript、React Flow、Tailwind CSS。
- 后端：FastAPI、SQLAlchemy、PostgreSQL、Redis。
- 异步任务：Celery + Redis。
- 网关与运行时：Agent Gateway、Context Engine、Skill Registry、MCP Registry、Memory Manager。
- 缓存：Reasonix 风格 Prefix-cache 友好 Prompt 编排 + Redis/数据库结果缓存。
- 部署：Docker Compose 起步，后续支持 Kubernetes。

## 文档入口

- [完整开发计划](docs/DEVELOPMENT_PLAN.md)
- [项目结构说明](docs/PROJECT_STRUCTURE.md)
- [开发规范](docs/DEVELOPMENT_GUIDE.md)
- [当前开发状态](docs/CURRENT_STATUS.md)
