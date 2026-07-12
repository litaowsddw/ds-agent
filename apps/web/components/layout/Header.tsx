/** 全局顶部工具栏。

显示当前页面标题、操作按钮和全局状态。
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Repeat2 } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import AgentContextSelect from "./AgentContextSelect";

export default function Header() {
  const router = useRouter();
  const workspace = useWorkspaceStore((s) => s.workspace);
  const setWorkspace = useWorkspaceStore((s) => s.setWorkspace);
  const busy = useWorkspaceStore((s) => s.busy);

  const handleSwitchWorkspace = () => {
    setWorkspace(null);
    router.push("/");
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-[#dfe4ee] bg-white px-6">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold text-[#172033]">
          {workspace ? `${workspace.email}` : "未选择工作区"}
        </h2>
        {workspace && (
          <span className="rounded-full bg-[#eef4ff] px-2 py-0.5 text-xs text-[#2f6feb]">
            {workspace.orgId.slice(0, 8)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {workspace && <AgentContextSelect />}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-[#667085]">
            <Loader2 className="animate-spin" size={14} />
            处理中...
          </div>
        )}
        {workspace ? (
          <button
            className="inline-flex h-8 items-center gap-2 rounded-lg border border-[#cfd7e6] bg-white px-3 text-xs font-medium text-[#344054] transition hover:border-[#2f6feb] hover:text-[#2f6feb]"
            onClick={handleSwitchWorkspace}
            type="button"
          >
            <Repeat2 size={14} />
            切换工作区
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
