"use client";

import { useReactFlow, useViewport } from "@xyflow/react";
import { CircleAlert, Grid3x3, Keyboard, Maximize, Minus, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { runWorkflowChecklist } from "@/lib/workflowChecklist";
import { useWorkflowStore } from "@/stores/workflow";

const SHORTCUTS: Array<[string, string]> = [
  ["Delete / Backspace", "删除选中节点或连线"],
  ["Ctrl/⌘ + Z", "撤销"],
  ["Ctrl/⌘ + Y 或 Ctrl/⌘ + Shift + Z", "重做"],
  ["Ctrl/⌘ + D", "复制选中节点"],
  ["Ctrl/⌘ + C / V", "复制 / 粘贴节点"],
  ["Ctrl/⌘ + A", "全选节点"],
  ["双击画布", "搜索并添加节点"],
  ["双击节点标题", "重命名节点"],
  ["右键节点 / 连线 / 画布", "上下文菜单"],
];

/** Dify operator bar: zoom controls, fit view, grid toggle, shortcut help. */
export default function CanvasOperatorBar({
  snapEnabled,
  onToggleSnap,
}: {
  snapEnabled: boolean;
  onToggleSnap: () => void;
}) {
  const { zoomIn, zoomOut, fitView, setCenter } = useReactFlow();
  const { zoom } = useViewport();
  const [helpOpen, setHelpOpen] = useState(false);
  const [checklistOpen, setChecklistOpen] = useState(false);
  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const setSelectedNodeId = useWorkflowStore((state) => state.setSelectedNodeId);

  const issues = useMemo(
    () => (checklistOpen ? runWorkflowChecklist(nodes, edges) : []),
    [checklistOpen, nodes, edges]
  );

  const jumpToNode = (nodeId: string | null) => {
    if (!nodeId) return;
    const node = useWorkflowStore.getState().nodes.find((item) => item.id === nodeId);
    if (!node) return;
    setSelectedNodeId(nodeId);
    void setCenter(node.position.x + 110, node.position.y + 48, { zoom: 1, duration: 300 });
  };

  const buttonClass =
    "inline-flex h-7 w-7 items-center justify-center rounded-md text-[#667085] transition hover:bg-[#f1f5f9] hover:text-[#172033]";

  return (
    <div className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-xl border border-[#dfe4ee] bg-white px-1.5 py-1 shadow-md">
      <button className={buttonClass} onClick={() => void zoomOut({ duration: 120 })} title="缩小" type="button">
        <Minus size={14} />
      </button>
      <button
        className="h-7 min-w-12 rounded-md px-1 text-center text-xs font-medium text-[#344054] transition hover:bg-[#f1f5f9]"
        onClick={() => void fitView({ duration: 200, padding: 0.22 })}
        title="恢复 100% 并适配视图"
        type="button"
      >
        {Math.round(zoom * 100)}%
      </button>
      <button className={buttonClass} onClick={() => void zoomIn({ duration: 120 })} title="放大" type="button">
        <Plus size={14} />
      </button>
      <button className={buttonClass} onClick={() => void fitView({ duration: 200, padding: 0.22 })} title="适配视图" type="button">
        <Maximize size={14} />
      </button>
      <span className="mx-0.5 h-4 w-px bg-[#eaecf0]" />
      <div className="relative">
        <button
          className={buttonClass}
          onClick={() => setChecklistOpen((open) => !open)}
          title="画布检查清单"
          type="button"
        >
          <CircleAlert size={14} />
        </button>
        {checklistOpen ? (
          <div className="absolute bottom-10 left-1/2 w-80 -translate-x-1/2 rounded-xl border border-[#dfe4ee] bg-white p-3 shadow-xl">
            <div className="mb-2 text-xs font-semibold text-[#172033]">检查清单</div>
            {issues.length === 0 ? (
              <div className="rounded-lg bg-[#ecfdf3] px-3 py-2 text-xs text-[#027a48]">画布配置没有发现问题</div>
            ) : (
              <ul className="max-h-56 space-y-1 overflow-y-auto">
                {issues.map((issue, index) => (
                  <li key={`${issue.nodeId}-${index}`}>
                    <button
                      className="w-full rounded-lg px-2.5 py-1.5 text-left text-xs text-[#b42318] transition hover:bg-[#fef3f2]"
                      onClick={() => jumpToNode(issue.nodeId)}
                      type="button"
                    >
                      {issue.message}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </div>
      <button
        className={`${buttonClass} ${snapEnabled ? "bg-[#eef4ff] text-[#175cd3]" : ""}`}
        onClick={onToggleSnap}
        title={snapEnabled ? "关闭网格吸附" : "开启网格吸附"}
        type="button"
      >
        <Grid3x3 size={14} />
      </button>
      <div className="relative">
        <button className={buttonClass} onClick={() => setHelpOpen((open) => !open)} title="快捷键" type="button">
          <Keyboard size={14} />
        </button>
        {helpOpen ? (
          <div className="absolute bottom-10 right-0 w-72 rounded-xl border border-[#dfe4ee] bg-white p-3 shadow-xl">
            <div className="mb-2 text-xs font-semibold text-[#172033]">快捷键</div>
            <dl className="space-y-1.5">
              {SHORTCUTS.map(([keys, action]) => (
                <div className="flex items-center justify-between gap-2" key={keys}>
                  <dt className="font-mono text-[11px] text-[#475467]">{keys}</dt>
                  <dd className="text-[11px] text-[#667085]">{action}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}
      </div>
    </div>
  );
}
