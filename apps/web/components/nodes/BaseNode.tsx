"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Bot,
  Braces,
  Code2,
  Database,
  FlagTriangleRight,
  GitBranch,
  Globe,
  Play,
  Plus,
  ShieldCheck,
  TextCursorInput,
  UserCheck,
} from "lucide-react";

export interface BaseNodeData extends Record<string, unknown> {
  label: string;
  icon?: React.ReactNode;
  description?: string;
  capability?: "executable" | "schema";
  runStatus?: string;
  onQuickAdd?: (nodeId: string, branch?: "true" | "false") => void;
  /** Inline rename state driven by the canvas. */
  renaming?: boolean;
  onRenameStart?: (nodeId: string) => void;
  onRenameSubmit?: (nodeId: string, name: string) => void;
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

const nodeIcons: Record<string, React.ComponentType<{ size?: number | string; className?: string }>> = {
  start: Play,
  end: FlagTriangleRight,
  llm: Bot,
  rag: Database,
  tool: ShieldCheck,
  condition: GitBranch,
  http: Globe,
  code: Code2,
  variable: Braces,
  template: TextCursorInput,
  human: UserCheck,
};

const nodeThemes: Record<string, { iconBg: string; text: string; accent: string }> = {
  start: { iconBg: "bg-[#22c55e]", text: "text-[#166534]", accent: "#22c55e" },
  end: { iconBg: "bg-[#ef4444]", text: "text-[#991b1b]", accent: "#ef4444" },
  llm: { iconBg: "bg-[#3b82f6]", text: "text-[#1e40af]", accent: "#3b82f6" },
  rag: { iconBg: "bg-[#eab308]", text: "text-[#854d0e]", accent: "#eab308" },
  tool: { iconBg: "bg-[#a855f7]", text: "text-[#6b21a8]", accent: "#a855f7" },
  condition: { iconBg: "bg-[#475569]", text: "text-[#334155]", accent: "#475569" },
  http: { iconBg: "bg-[#0891b2]", text: "text-[#155e75]", accent: "#0891b2" },
  code: { iconBg: "bg-[#57534e]", text: "text-[#44403c]", accent: "#57534e" },
  variable: { iconBg: "bg-[#0d9488]", text: "text-[#115e59]", accent: "#0d9488" },
  template: { iconBg: "bg-[#f97316]", text: "text-[#9a3412]", accent: "#f97316" },
  human: { iconBg: "bg-[#db2777]", text: "text-[#9d174d]", accent: "#db2777" },
};

export function getNodeSetupState(nodeType: string, data: Record<string, unknown>): { ready: boolean; hint: string } {
  const config = (data.config ?? {}) as Record<string, unknown>;
  if (data.capability === "schema") return { ready: false, hint: "设计中" };
  if (nodeType === "llm" && (!config.provider || !config.model)) return { ready: false, hint: "选择模型" };
  if (nodeType === "rag" && !config.kb_id) return { ready: false, hint: "选择知识库" };
  if (nodeType === "tool" && !config.tool_id) return { ready: false, hint: "选择工具" };
  if (nodeType === "condition" && (!config.left || !config.operator)) return { ready: false, hint: "配置条件" };
  return { ready: true, hint: "就绪" };
}

function truncate(text: string, max = 42): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function summarizeConfig(nodeType: string, data: BaseNodeData): string[] {
  const config = (data.config ?? {}) as Record<string, unknown>;
  const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");
  switch (nodeType) {
    case "llm": {
      const model = text(config.model) || "未选择模型";
      const prompt = text(config.prompt);
      return prompt ? [model, truncate(prompt)] : [model];
    }
    case "rag": {
      const kb = text(config.kb_id) || "未选择知识库";
      return [`知识库 ${kb}`, `上限 ${String(config.limit ?? 5)} 条`];
    }
    case "tool": {
      const name = text(config.tool_name) || text(config.tool_id) || "未选择工具";
      return [name, `风险 ${String(config.risk_level ?? "low")}`];
    }
    case "condition": {
      const left = text(config.left) || "未选择数据";
      const operator = text(config.operator) || "equals";
      const value = operator === "exists" ? "非空" : String(config.value ?? "");
      return [truncate(`${left} ${operator} ${value}`.trim(), 48)];
    }
    case "http":
      return [`${text(config.method) || "GET"} ${truncate(text(config.url), 32)}`.trim()];
    case "code":
      return [text(config.language) || "python"];
    case "variable":
      return [text(config.name) || "value"];
    case "human":
      return [truncate(text(config.title) || "人工审批")];
    case "template":
      return [truncate(text(config.template))].filter(Boolean);
    default:
      return [];
  }
}

const runStatusStyles: Record<string, { label: string; ring: string; badge: string }> = {
  running: { label: "运行中", ring: "ring-2 ring-[#2f6feb] animate-pulse", badge: "bg-[#eef4ff] text-[#175cd3]" },
  succeeded: { label: "成功", ring: "ring-2 ring-[#12b76a]", badge: "bg-[#ecfdf3] text-[#027a48]" },
  failed: { label: "失败", ring: "ring-2 ring-[#f04438]", badge: "bg-[#fef3f2] text-[#b42318]" },
  skipped: { label: "跳过", ring: "ring-1 ring-[#cbd5e1]", badge: "bg-[#f8fafc] text-[#667085]" },
  pending: { label: "待执行", ring: "ring-1 ring-[#cbd5e1]", badge: "bg-[#f8fafc] text-[#667085]" },
};

function QuickAddButton({
  branch,
  nodeId,
  onQuickAdd,
  top,
}: {
  branch?: "true" | "false";
  nodeId: string;
  onQuickAdd: (nodeId: string, branch?: "true" | "false") => void;
  top: string;
}) {
  return (
    <button
      aria-label={branch ? `在 ${branch} 分支后添加节点` : "在此节点后添加节点"}
      className="absolute -right-11 z-10 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-full border border-[#cfd7e6] bg-white text-[#2f6feb] opacity-0 shadow-sm transition hover:border-[#2f6feb] hover:bg-[#eef4ff] focus:opacity-100 group-hover:opacity-100"
      onClick={(event) => {
        event.stopPropagation();
        onQuickAdd(nodeId, branch);
      }}
      style={{ top }}
      type="button"
    >
      <Plus size={15} />
    </button>
  );
}

function BaseNode({ data, id, type, selected }: NodeProps) {
  const nodeType = type ?? "llm";
  const nodeId = String(id ?? "");
  const nodeData = data as BaseNodeData;
  const display = getNodeDisplay(nodeData);
  const theme = nodeThemes[nodeType] ?? nodeThemes.llm;
  const Icon = nodeIcons[nodeType] ?? Bot;
  const setup = getNodeSetupState(nodeType, nodeData);
  const summary = summarizeConfig(nodeType, nodeData);
  const runStatus = typeof nodeData.runStatus === "string" ? runStatusStyles[nodeData.runStatus] : undefined;
  const onQuickAdd = nodeData.onQuickAdd;

  const submitRename = (raw: string) => {
    nodeData.onRenameSubmit?.(nodeId, raw.trim());
  };

  return (
    <div className="group relative">
      <div
        className={`relative w-[220px] rounded-xl border bg-white px-3.5 py-3 shadow-sm transition-shadow hover:shadow-md ${
          selected ? "border-[#2f6feb] ring-2 ring-[#2f6feb]/30" : "border-[#dfe4ee]"
        } ${runStatus ? runStatus.ring : ""}`}
        style={runStatus || selected ? undefined : { borderTopColor: theme.accent, borderTopWidth: 3 }}
      >
        {nodeType !== "start" ? (
          <Handle
            type="target"
            position={Position.Left}
            className="!h-3.5 !w-3.5 !rounded-full !border-2 !border-white !bg-[#94a3b8] hover:!bg-[#2f6feb]"
          />
        ) : null}

        <div className="flex items-center gap-2.5">
          <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg text-white ${theme.iconBg}`}>
            <Icon size={17} />
          </div>
          <div className="min-w-0 flex-1">
            {nodeData.renaming ? (
              <input
                autoFocus
                className="nodrag w-full rounded border border-[#2f6feb] px-1 py-0.5 text-sm font-semibold text-[#172033] outline-none"
                defaultValue={display.label}
                onBlur={(event) => submitRename(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") submitRename((event.target as HTMLInputElement).value);
                  if (event.key === "Escape") nodeData.onRenameSubmit?.(nodeId, display.label);
                }}
              />
            ) : (
              <div
                className="truncate text-sm font-semibold text-[#172033]"
                onDoubleClick={(event) => {
                  event.stopPropagation();
                  nodeData.onRenameStart?.(nodeId);
                }}
                title="双击重命名"
              >
                {display.label}
              </div>
            )}
            <div className="truncate text-[11px] uppercase tracking-wide text-[#98a2b3]">{nodeType}</div>
          </div>
          <span
            className={`h-2.5 w-2.5 shrink-0 rounded-full ${setup.ready ? "bg-[#12b76a]" : "bg-[#f79009]"}`}
            title={setup.ready ? "配置就绪" : `待配置：${setup.hint}`}
          />
        </div>

        {summary.length > 0 ? (
          <div className="mt-2.5 space-y-1 border-t border-[#eef1f6] pt-2.5">
            {summary.map((line) => (
              <div key={line} className="truncate text-xs leading-4 text-[#667085]" title={line}>
                {line}
              </div>
            ))}
          </div>
        ) : display.description ? (
          <div className="mt-2.5 border-t border-[#eef1f6] pt-2.5 text-xs leading-4 text-[#667085]">
            {truncate(display.description)}
          </div>
        ) : null}

        {runStatus ? (
          <div className="mt-2.5 border-t border-[#eef1f6] pt-2">
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${runStatus.badge}`}>
              {runStatus.label}
            </span>
          </div>
        ) : null}

        {nodeType === "condition" ? (
          <>
            <span className="absolute right-3 top-[55%] -translate-y-1/2 text-[10px] font-semibold text-[#027a48]">true</span>
            <Handle
              id="true"
              type="source"
              position={Position.Right}
              style={{ top: "55%" }}
              className="!h-3.5 !w-3.5 !rounded-full !border-2 !border-white !bg-[#22c55e]"
            />
            <span className="absolute right-3 top-[78%] -translate-y-1/2 text-[10px] font-semibold text-[#b42318]">false</span>
            <Handle
              id="false"
              type="source"
              position={Position.Right}
              style={{ top: "78%" }}
              className="!h-3.5 !w-3.5 !rounded-full !border-2 !border-white !bg-[#ef4444]"
            />
          </>
        ) : nodeType !== "end" ? (
          <Handle
            type="source"
            position={Position.Right}
            className="!h-3.5 !w-3.5 !rounded-full !border-2 !border-white !bg-[#94a3b8] hover:!bg-[#2f6feb]"
          />
        ) : null}
      </div>

      {onQuickAdd && nodeType !== "end" ? (
        nodeType === "condition" ? (
          <>
            <QuickAddButton branch="true" nodeId={nodeId} onQuickAdd={onQuickAdd} top="55%" />
            <QuickAddButton branch="false" nodeId={nodeId} onQuickAdd={onQuickAdd} top="78%" />
          </>
        ) : (
          <QuickAddButton nodeId={nodeId} onQuickAdd={onQuickAdd} top="50%" />
        )
      ) : null}
    </div>
  );
}

export default memo(BaseNode);
