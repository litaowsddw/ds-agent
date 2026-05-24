import { Activity, Bot, Boxes, GitBranch, ShieldCheck, Workflow } from "lucide-react";

// capabilityItems 表示首页展示的核心能力清单，后续可以替换为从 API 读取的模块状态。
const capabilityItems = [
  {
    title: "可视化工作流",
    description: "用画布组织 Start、LLM、RAG、Tool、Condition、End 等节点。",
    icon: Workflow
  },
  {
    title: "Agent Runtime",
    description: "按 Agent 隔离 Workspace、Session、Skill、MCP 和 Memory。",
    icon: Bot
  },
  {
    title: "异步任务调度",
    description: "基于 Celery + Redis 支撑排队、重试、超时和后台 Agent。",
    icon: Activity
  },
  {
    title: "统一网关",
    description: "所有 LLM、RAG、工具和 MCP 调用统一鉴权、限流、审计。",
    icon: ShieldCheck
  },
  {
    title: "Reasonix 缓存友好",
    description: "稳定前缀、追加历史、动态输入后置，提升 prefix-cache 命中。",
    icon: GitBranch
  },
  {
    title: "模块化扩展",
    description: "按 MVP 模块独立开发、独立测试，逐步演进到完整平台。",
    icon: Boxes
  }
];

export default function HomePage() {
  // sidebarItems 表示工作台左侧导航项，MVP 阶段先使用静态数据。
  const sidebarItems = ["总览", "Agent", "Workflow", "Runtime", "MCP", "Memory", "任务队列"];

  return (
    <main className="min-h-screen bg-canvas">
      <section className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded bg-accent text-white">
              <Workflow size={20} />
            </div>
            <div>
              <h1 className="text-lg font-semibold">AgentFlow</h1>
              <p className="text-sm text-muted">开源 Agent 工作流平台</p>
            </div>
          </div>
          <div className="rounded border border-line px-3 py-1 text-sm text-muted">v0.1 骨架开发中</div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl grid-cols-[280px_1fr] gap-6 px-6 py-6">
        <aside className="h-[calc(100vh-120px)] border-r border-line pr-5">
          <nav className="space-y-2">
            {sidebarItems.map((item) => (
              <button
                key={item}
                className="flex w-full items-center justify-between rounded border border-transparent px-3 py-2 text-left text-sm text-ink hover:border-line hover:bg-white"
              >
                <span>{item}</span>
              </button>
            ))}
          </nav>
        </aside>

        <div className="space-y-6">
          <section className="grid grid-cols-[1.1fr_0.9fr] gap-6">
            <div className="border-b border-line pb-6">
              <p className="mb-3 text-sm font-medium text-accent">MVP 第一阶段</p>
              <h2 className="mb-4 text-3xl font-semibold tracking-normal">先完成可运行骨架，再逐步接入运行时能力</h2>
              <p className="max-w-3xl text-base leading-7 text-muted">
                当前版本聚焦 API、Worker、Runtime 抽象和工作台入口。后续每个模块独立开发、独立测试，最终形成支持多用户、
                多 Agent、多工作流和高并发异步执行的开源框架。
              </p>
            </div>
            <div className="border border-line bg-panel p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-medium">主链路</span>
                <span className="text-xs text-muted">设计中</span>
              </div>
              <ol className="space-y-3 text-sm text-muted">
                <li>1. 创建组织与 Agent</li>
                <li>2. 配置 Workspace、Skill、MCP</li>
                <li>3. 可视化搭建 Workflow</li>
                <li>4. Celery 异步执行任务</li>
                <li>5. Gateway 统一调用 LLM/RAG/Tool</li>
                <li>6. 展示上下文、限流、缓存和运行轨迹</li>
              </ol>
            </div>
          </section>

          <section className="grid grid-cols-3 gap-4">
            {capabilityItems.map((item) => {
              const Icon = item.icon;
              return (
                <article key={item.title} className="border border-line bg-panel p-4">
                  <div className="mb-4 flex h-9 w-9 items-center justify-center rounded border border-line text-accent">
                    <Icon size={18} />
                  </div>
                  <h3 className="mb-2 text-sm font-semibold">{item.title}</h3>
                  <p className="text-sm leading-6 text-muted">{item.description}</p>
                </article>
              );
            })}
          </section>
        </div>
      </section>
    </main>
  );
}
