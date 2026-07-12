/** 应用全局布局。

Dify 风格布局：左侧固定侧边栏 + 右侧主内容区。
包含 Toast 提示系统和工作空间初始化检测。
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "./Sidebar";
import Header from "./Header";
import MobileNavOverlay from "./MobileNavOverlay";
import { useWorkspaceStore } from "@/stores/workspace";
import { checkHealth } from "@/lib/api";
import type { ToastKind } from "@/types/api";

/** Toast 通知组件 */
function Toast({
  kind,
  text,
  onClose,
}: {
  kind: ToastKind;
  text: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const timer = setTimeout(onClose, 4000);
    return () => clearTimeout(timer);
  }, [onClose]);

  const cls = {
    success: "border-[#bbf7d0] bg-[#f0fdf4] text-[#047857]",
    error: "border-[#fecaca] bg-[#fef2f2] text-[#b42318]",
    info: "border-[#dfe4ee] bg-[#f8fafc] text-[#344054]",
  }[kind];

  return (
    <div className={`fixed bottom-4 right-4 z-50 rounded-lg border p-3 text-sm shadow-lg ${cls}`}>
      {text}
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const workspace = useWorkspaceStore((s) => s.workspace);
  const setApiStatus = useWorkspaceStore((s) => s.setApiStatus);

  const [toast, setToast] = useState<{ kind: ToastKind; text: string } | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const closeNavigation = useCallback(() => setNavigationOpen(false), []);

  useEffect(() => {
    setNavigationOpen(false);
  }, [pathname]);

  // 检测 API 状态
  useEffect(() => {
    let mounted = true;
    async function check() {
      try {
        const res = await checkHealth();
        if (mounted) setApiStatus(res.status === "ok" ? "online" : "offline");
      } catch {
        if (mounted) setApiStatus("offline");
      }
    }
    void check();
    const interval = setInterval(() => void check(), 30000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [setApiStatus]);

  // 全局 Toast 监听
  useEffect(() => {
    function handler(e: CustomEvent<{ kind: ToastKind; text: string }>) {
      setToast(e.detail);
    }
    window.addEventListener("agentflow-toast" as string, handler as EventListener);
    return () =>
      window.removeEventListener("agentflow-toast" as string, handler as EventListener);
  }, []);

  return (
    <div className="flex h-dvh bg-[#f6f7f9] text-[#172033]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header
          navigationOpen={navigationOpen}
          onOpenNavigation={() => setNavigationOpen(true)}
        />
        <main className="min-h-0 min-w-0 flex-1 overflow-auto p-3 sm:p-6">{children}</main>
      </div>
      <MobileNavOverlay open={navigationOpen} onClose={closeNavigation} />
      {toast && (
        <Toast kind={toast.kind} text={toast.text} onClose={() => setToast(null)} />
      )}
    </div>
  );
}

/** 全局发送 Toast 的工具函数 */
export function showToast(kind: ToastKind, text: string) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("agentflow-toast", { detail: { kind, text } }));
  }
}
