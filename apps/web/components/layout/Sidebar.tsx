/** 全局侧边栏导航。

Dify 风格的左侧导航栏，包含 Logo、API 状态、导航菜单和 Toast 提示。
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  Brain,
  Database,
  House,
  KeyRound,
  MessageSquare,
  Network,
  PlugZap,
  Workflow,
} from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";

const navItems = [
  { key: "home", label: "Home", icon: House, href: "/" },
  { key: "agents", label: "Agents", icon: Bot, href: "/agents" },
  { key: "models", label: "Models", icon: KeyRound, href: "/models" },
  { key: "knowledge", label: "Knowledge", icon: Database, href: "/knowledge" },
  { key: "tools", label: "Tools", icon: PlugZap, href: "/tools" },
  { key: "workflow", label: "Workflow", icon: Workflow, href: "/workflows" },
  { key: "runs", label: "Runs", icon: Activity, href: "/runs" },
  { key: "runtime", label: "Runtime", icon: Brain, href: "/runtime" },
  { key: "chat", label: "Chat", icon: MessageSquare, href: "/chat" },
] as const;

function StatusPill({ status }: { status: "checking" | "online" | "offline" }) {
  const text = { checking: "检测中", online: "在线", offline: "离线" }[status];
  const cls = {
    checking: "bg-[#fff7ed] text-[#c2410c]",
    online: "bg-[#ecfdf3] text-[#027a48]",
    offline: "bg-[#fef2f2] text-[#b42318]",
  }[status];
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${cls}`}>{text}</span>;
}

export default function Sidebar({
  mobile = false,
  onNavigate,
}: {
  mobile?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const apiStatus = useWorkspaceStore((s) => s.apiStatus);

  return (
    <aside
      className={`${mobile ? "flex h-full w-full" : "hidden h-screen w-[260px] lg:flex"} shrink-0 flex-col border-r border-[#dfe4ee] bg-white`}
    >
      {/* Logo */}
      <Link
        className="flex items-center gap-3 border-b border-[#dfe4ee] px-5 py-4 transition hover:bg-[#f8fafc]"
        href="/"
        onClick={onNavigate}
      >
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#2f6feb] text-white">
          <Network size={19} />
        </div>
        <div>
          <h1 className="text-base font-semibold text-[#172033]">AgentFlow</h1>
          <p className="text-xs text-[#667085]">Agent 应用搭建工作台</p>
        </div>
      </Link>

      {/* API 状态 */}
      <div className="mx-4 mt-4 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-[#667085]">API 状态</span>
          <StatusPill status={apiStatus} />
        </div>
        <p className="text-xs leading-5 text-[#667085]">
          {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:18000"}
        </p>
      </div>

      {/* 导航 */}
      <nav className="mt-4 flex-1 space-y-1 px-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active =
            item.href === "/" ? pathname === "/" : pathname === item.href || pathname?.startsWith(item.href + "/");
          return (
            <Link
              key={item.key}
              href={item.href}
              onClick={onNavigate}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition ${
                active
                  ? "bg-[#eef4ff] font-medium text-[#2f6feb]"
                  : "text-[#344054] hover:bg-[#f8fafc]"
              }`}
            >
              <Icon size={16} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* 底部信息 */}
      <div className="border-t border-[#dfe4ee] px-4 py-3">
        <p className="text-xs text-[#667085]">AgentFlow v0.1</p>
      </div>
    </aside>
  );
}
