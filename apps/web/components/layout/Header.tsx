/** 全局顶部工具栏。

显示当前页面标题、操作按钮和全局状态。
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Menu, Repeat2 } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import AgentContextSelect from "./AgentContextSelect";

export default function Header({
  navigationOpen,
  onOpenNavigation,
}: {
  navigationOpen: boolean;
  onOpenNavigation: () => void;
}) {
  const router = useRouter();
  const workspace = useWorkspaceStore((s) => s.workspace);
  const setWorkspace = useWorkspaceStore((s) => s.setWorkspace);
  const busy = useWorkspaceStore((s) => s.busy);

  const handleSwitchWorkspace = () => {
    setWorkspace(null);
    router.push("/");
  };

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-[#dfe4ee] bg-white px-3 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          aria-controls="mobile-navigation"
          aria-expanded={navigationOpen}
          aria-label="Open navigation"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#cfd7e6] text-[#344054] lg:hidden"
          onClick={onOpenNavigation}
          type="button"
        >
          <Menu size={17} />
        </button>
        <h2 className="hidden truncate text-sm font-semibold text-[#172033] sm:block">
          {workspace ? `${workspace.email}` : "未选择工作区"}
        </h2>
        {workspace && (
          <span className="hidden rounded-full bg-[#eef4ff] px-2 py-0.5 text-xs text-[#2f6feb] md:inline">
            {workspace.orgId.slice(0, 8)}
          </span>
        )}
      </div>
      <div className="flex min-w-0 items-center gap-1.5 sm:gap-3">
        {workspace && (
          <div className="min-w-0 [&_select]:max-w-[150px] [&_select]:min-w-0 sm:[&_select]:max-w-none sm:[&_select]:min-w-[180px]">
            <AgentContextSelect />
          </div>
        )}
        {busy && (
          <div className="hidden items-center gap-2 text-xs text-[#667085] md:flex">
            <Loader2 className="animate-spin" size={14} />
            处理中...
          </div>
        )}
        {workspace ? (
          <button
            aria-label="切换工作区"
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center gap-2 rounded-lg border border-[#cfd7e6] bg-white text-xs font-medium text-[#344054] transition hover:border-[#2f6feb] hover:text-[#2f6feb] sm:w-auto sm:px-3"
            onClick={handleSwitchWorkspace}
            type="button"
          >
            <Repeat2 size={14} />
            <span className="hidden sm:inline">切换工作区</span>
          </button>
        ) : (
          <Link
            className="inline-flex h-8 items-center justify-center rounded-lg bg-[#2f6feb] px-3 text-xs font-medium text-white transition hover:bg-[#255dc7]"
            href="/"
          >
            选择/创建工作区
          </Link>
        )}
      </div>
    </header>
  );
}
