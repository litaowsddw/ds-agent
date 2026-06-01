/** 自定义 React Flow 节点基础组件。

所有自定义节点共享的基础样式：圆角卡片、图标、标签、连接手柄。
 */

"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface BaseNodeData extends Record<string, unknown> {
  label: string;
  icon?: React.ReactNode;
  description?: string;
}

/** 节点颜色配置 */
const nodeThemes: Record<string, { bg: string; border: string; iconBg: string; text: string }> = {
  start: { bg: "bg-[#f0fdf4]", border: "border-[#86efac]", iconBg: "bg-[#22c55e]", text: "text-[#166534]" },
  end: { bg: "bg-[#fef2f2]", border: "border-[#fca5a5]", iconBg: "bg-[#ef4444]", text: "text-[#991b1b]" },
  llm: { bg: "bg-[#eef4ff]", border: "border-[#93c5fd]", iconBg: "bg-[#3b82f6]", text: "text-[#1e40af]" },
  rag: { bg: "bg-[#fefce8]", border: "border-[#fde047]", iconBg: "bg-[#eab308]", text: "text-[#854d0e]" },
  tool: { bg: "bg-[#faf5ff]", border: "border-[#d8b4fe]", iconBg: "bg-[#a855f7]", text: "text-[#6b21a8]" },
};

function BaseNode({ data, type }: NodeProps & { type?: string }) {
  const label = String(data.label ?? "");
  const theme = nodeThemes[type ?? "llm"] ?? nodeThemes.llm;

  return (
    <div
      className={`min-w-[140px] rounded-xl border-2 ${theme.border} ${theme.bg} px-4 py-3 shadow-sm transition-shadow hover:shadow-md`}
    >
      {/* 输入手柄 - 非起始节点 */}
      {type !== "start" && (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
        />
      )}

      <div className="flex items-center gap-2">
        <div
          className={`grid h-7 w-7 place-items-center rounded-md ${theme.iconBg} text-white`}
        >
          {data.icon as React.ReactNode ?? null}
        </div>
        <div>
          <div className={`text-sm font-semibold ${theme.text}`}>{label}</div>
          {data.description ? (
            <div className="text-xs text-[#667085]">{String(data.description)}</div>
          ) : null}
        </div>
      </div>

      {/* 输出手柄 - 非结束节点 */}
      {type !== "end" && (
        <Handle
          type="source"
          position={Position.Right}
          className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
        />
      )}
    </div>
  );
}

export default memo(BaseNode);
