import Link from "next/link";
import { Activity, Bot, Database, GitBranch, Network, ShieldCheck, Workflow } from "lucide-react";

const capabilityItems = [
  { title: "可视化工作流", description: "拖拽节点、保存草稿、发布版本并立即运行。", icon: Workflow },
  { title: "Agent 隔离", description: "按用户、组织、群组和 Agent 绑定运行边界。", icon: Bot },
  { title: "异步执行", description: "Celery + Redis 支撑排队、重试和后台任务。", icon: Activity },
  { title: "统一网关", description: "统一管理 LLM、RAG、工具和 MCP 调用。", icon: ShieldCheck },
  { title: "缓存友好", description: "稳定前缀、追加历史和动态输入后置。", icon: GitBranch },
  { title: "记忆管理", description: "长期记忆、偏好事实和上下文装配逐步完善。", icon: Database }
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[#f6f7f9] text-[#172033]">
      <header className="border-b border-[#dfe4ee] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#2f6feb] text-white">
              <Network size={20} />
            </div>
            <div>
              <h1 className="text-lg font-semibold">AgentFlow</h1>
              <p className="text-sm text-[#667085]">开源 Agent 工作流平台</p>
            </div>
          </div>
          <Link
            className="rounded-md bg-[#2f6feb] px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[#255dc7]"
            href="/workflows"
          >
            进入工作台
          </Link>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl grid-cols-[1fr_420px] gap-8 px-6 py-10">
        <div className="flex min-h-[520px] flex-col justify-center border-b border-[#dfe4ee] pb-10">
          <p className="mb-4 text-sm font-semibold text-[#2f6feb]">MVP 联调版本</p>
          <h2 className="max-w-4xl text-4xl font-semibold leading-tight">
            从组织、Agent 到工作流运行，一条链路完成可视化搭建与后端执行。
          </h2>
          <p className="mt-5 max-w-3xl text-base leading-7 text-[#667085]">
            当前阶段聚焦可运行骨架：前端提供清爽的工作台入口，后端提供身份隔离、Agent Workspace、
            Workflow 发布运行、Gateway 日志和限流能力。后续模块会按开发文档继续独立开发、独立测试、整体联调。
          </p>
          <div className="mt-7 flex gap-3">
            <Link
              className="rounded-md bg-[#2f6feb] px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[#255dc7]"
              href="/workflows"
            >
              打开工作流编辑器
            </Link>
            <a
              className="rounded-md border border-[#cfd7e6] bg-white px-4 py-2 text-sm font-medium text-[#172033] transition hover:border-[#2f6feb]"
              href="http://127.0.0.1:8000/docs"
              target="_blank"
            >
              查看 API 文档
            </a>
          </div>
        </div>

        <aside className="self-center rounded-lg border border-[#dfe4ee] bg-white p-5 shadow-sm">
          <div className="mb-5 flex items-center justify-between">
            <h3 className="text-sm font-semibold">联调主链路</h3>
            <span className="rounded-full bg-[#eef4ff] px-2.5 py-1 text-xs font-medium text-[#2f6feb]">
              ready
            </span>
          </div>
          <ol className="space-y-4 text-sm text-[#667085]">
            <li className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#eef4ff] text-xs text-[#2f6feb]">1</span>
              注册本地测试用户并创建组织
            </li>
            <li className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#eef4ff] text-xs text-[#2f6feb]">2</span>
              创建 Agent 和默认 Workspace
            </li>
            <li className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#eef4ff] text-xs text-[#2f6feb]">3</span>
              保存画布为 Workflow DSL
            </li>
            <li className="flex gap-3">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#eef4ff] text-xs text-[#2f6feb]">4</span>
              发布版本并同步执行一次
            </li>
          </ol>
        </aside>
      </section>

      <section className="mx-auto grid max-w-7xl grid-cols-3 gap-4 px-6 pb-10">
        {capabilityItems.map((item) => {
          const Icon = item.icon;
          return (
            <article key={item.title} className="rounded-lg border border-[#dfe4ee] bg-white p-5 shadow-sm">
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-md border border-[#dfe4ee] text-[#2f6feb]">
                <Icon size={18} />
              </div>
              <h3 className="mb-2 text-sm font-semibold">{item.title}</h3>
              <p className="text-sm leading-6 text-[#667085]">{item.description}</p>
            </article>
          );
        })}
      </section>
    </main>
  );
}
