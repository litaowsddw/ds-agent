/** 全局顶部工具栏。

显示当前页面标题、操作按钮和全局状态。
 */

"use client";

import { Loader2, Plus } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";

export default function Header() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const busy = useWorkspaceStore((s) => s.busy);

  return (
    <header className="flex h-14 items-center justify-between border-b border-[#dfe4ee] bg-white px-6">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold text-[#172033]">
          {workspace ? `${workspace.email}` : "请先创建工作空间"}
        </h2>
        {workspace && (
          <span className="rounded-full bg-[#eef4ff] px-2 py-0.5 text-xs text-[#2f6feb]">
            {workspace.orgId.slice(0, 8)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {busy && (
          <div className="flex items-center gap-2 text-xs text-[#667085]">
            <Loader2 className="animate-spin" size={14} />
            处理中...
          </div>
        )}
      </div>
    </header>
  );
}
