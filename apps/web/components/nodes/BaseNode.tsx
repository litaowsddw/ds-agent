"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface BaseNodeData extends Record<string, unknown> {
  label: string;
  icon?: React.ReactNode;
  description?: string;
  capability?: "executable" | "schema";
}

/**
 * Node labels used to be fixed by the node type, which made a canvas with
 * several LLM or Tool nodes difficult to read.  Keep the runner-facing type
 * stable, while allowing workflow authors to give the visual step a durable
 * identity in its saved config.
 */
export function getNodeDisplay(data: BaseNodeData): { description: string; label: string } {
  const config = (data.config ?? {}) as Record<string, unknown>;
  const configuredLabel = typeof config.display_name === "string" ? config.display_name.trim() : "";
  const configuredDescription =
    typeof config.display_description === "string" ? config.display_description.trim() : "";

  return {
    label: configuredLabel || data.label,
    description: configuredDescription || String(data.description ?? ""),
  };
}

const nodeThemes: Record<string, { bg: string; border: string; iconBg: string; text: string }> = {
  start: { bg: "bg-[#f0fdf4]", border: "border-[#86efac]", iconBg: "bg-[#22c55e]", text: "text-[#166534]" },
  end: { bg: "bg-[#fef2f2]", border: "border-[#fca5a5]", iconBg: "bg-[#ef4444]", text: "text-[#991b1b]" },
  llm: { bg: "bg-[#eef4ff]", border: "border-[#93c5fd]", iconBg: "bg-[#3b82f6]", text: "text-[#1e40af]" },
  rag: { bg: "bg-[#fefce8]", border: "border-[#fde047]", iconBg: "bg-[#eab308]", text: "text-[#854d0e]" },
  tool: { bg: "bg-[#faf5ff]", border: "border-[#d8b4fe]", iconBg: "bg-[#a855f7]", text: "text-[#6b21a8]" },
  condition: { bg: "bg-[#f8fafc]", border: "border-[#cbd5e1]", iconBg: "bg-[#475569]", text: "text-[#334155]" },
  http: { bg: "bg-[#ecfeff]", border: "border-[#67e8f9]", iconBg: "bg-[#0891b2]", text: "text-[#155e75]" },
  code: { bg: "bg-[#f5f5f4]", border: "border-[#d6d3d1]", iconBg: "bg-[#57534e]", text: "text-[#44403c]" },
  variable: { bg: "bg-[#f0fdfa]", border: "border-[#5eead4]", iconBg: "bg-[#0d9488]", text: "text-[#115e59]" },
  template: { bg: "bg-[#fff7ed]", border: "border-[#fdba74]", iconBg: "bg-[#f97316]", text: "text-[#9a3412]" },
  human: { bg: "bg-[#fdf2f8]", border: "border-[#f9a8d4]", iconBg: "bg-[#db2777]", text: "text-[#9d174d]" },
};

function getNodeStatus(nodeType: string, data: Record<string, unknown>) {
  const config = (data.config ?? {}) as Record<string, unknown>;
  if (data.capability === "schema") return { label: "schema", tone: "bg-[#f8fafc] text-[#667085]" };
  if (nodeType === "llm" && (!config.provider || !config.model)) {
    return { label: "setup", tone: "bg-[#fff7ed] text-[#c2410c]" };
  }
  if (nodeType === "rag" && !config.kb_id) {
    return { label: "setup", tone: "bg-[#fff7ed] text-[#c2410c]" };
  }
  if (nodeType === "tool" && !config.tool_id) {
    return { label: "setup", tone: "bg-[#fff7ed] text-[#c2410c]" };
  }
  if (nodeType === "condition" && (!config.left || !config.operator)) {
    return { label: "setup", tone: "bg-[#fff7ed] text-[#c2410c]" };
  }
  return { label: "ready", tone: "bg-[#ecfdf3] text-[#027a48]" };
}

function BaseNode({ data, type }: NodeProps & { type?: string }) {
  const nodeType = type ?? "llm";
  const display = getNodeDisplay(data as BaseNodeData);
  const label = display.label;
  const theme = nodeThemes[nodeType] ?? nodeThemes.llm;
  const status = getNodeStatus(nodeType, data);

  return (
    <div
      className={`relative min-w-[188px] rounded-lg border-2 ${theme.border} ${theme.bg} px-4 py-3 shadow-sm transition-shadow hover:shadow-md`}
    >
      {nodeType !== "start" ? (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
        />
      ) : null}

      <div className="flex items-center gap-2">
        <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-md ${theme.iconBg} text-xs font-semibold text-white`}>
          {String(label).slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className={`truncate text-sm font-semibold ${theme.text}`}>{label}</div>
          {display.description ? <div className="truncate text-xs text-[#667085]">{display.description}</div> : null}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-normal ${status.tone}`}>
          {status.label}
        </span>
        <span className="truncate text-[10px] font-medium text-[#667085]">
          {nodeType}
        </span>
      </div>

      {nodeType === "condition" ? (
        <>
          <span className="absolute right-4 top-[42%] -translate-y-1/2 text-[10px] font-semibold text-[#027a48]">true</span>
          <Handle
            id="true"
            type="source"
            position={Position.Right}
            style={{ top: "42%" }}
            className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#22c55e]"
          />
          <span className="absolute right-4 top-[72%] -translate-y-1/2 text-[10px] font-semibold text-[#b42318]">false</span>
          <Handle
            id="false"
            type="source"
            position={Position.Right}
            style={{ top: "72%" }}
            className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#ef4444]"
          />
        </>
      ) : nodeType !== "end" ? (
        <Handle
          type="source"
          position={Position.Right}
          className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
        />
      ) : null}
    </div>
  );
}

export default memo(BaseNode);
