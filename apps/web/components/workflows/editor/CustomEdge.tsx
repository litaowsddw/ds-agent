"use client";

import { memo, useState } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  Position,
  type EdgeProps,
} from "@xyflow/react";
import { Plus } from "lucide-react";

export interface CustomEdgeData extends Record<string, unknown> {
  branch?: "true" | "false";
  onInsertNode?: (edgeId: string, flowPosition: { x: number; y: number }) => void;
}

/**
 * Dify-style edge (custom-edge.tsx): a bezier curve whose midpoint shows a
 * "+" trigger on hover/selection to insert a node into the connection, plus
 * a branch badge for Condition outputs.
 */
function CustomEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  selected,
  data,
}: EdgeProps) {
  const [hovered, setHovered] = useState(false);
  const edgeData = (data ?? {}) as CustomEdgeData;
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition: Position.Right,
    targetX,
    targetY,
    targetPosition: Position.Left,
    curvature: 0.16,
  });

  const stroke = selected ? "#2f6feb" : hovered ? "#84adff" : "#94a3b8";
  const branch = edgeData.branch;

  return (
    <g onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      <BaseEdge
        id={id}
        path={edgePath}
        interactionWidth={20}
        style={{ stroke, strokeWidth: selected ? 2.5 : 2, transition: "stroke 120ms" }}
      />
      <EdgeLabelRenderer>
        <div
          className="nopan nodrag pointer-events-none absolute flex items-center gap-1"
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
        >
          {branch ? (
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                branch === "true" ? "bg-[#ecfdf3] text-[#027a48]" : "bg-[#fef3f2] text-[#b42318]"
              }`}
            >
              {branch}
            </span>
          ) : null}
          {edgeData.onInsertNode && (hovered || selected) ? (
            <button
              aria-label="在连线中插入节点"
              className="pointer-events-auto grid h-5 w-5 place-items-center rounded-full border border-[#cfd7e6] bg-white text-[#2f6feb] shadow-sm transition hover:scale-125 hover:border-[#2f6feb]"
              onClick={(event) => {
                event.stopPropagation();
                edgeData.onInsertNode?.(id, { x: labelX, y: labelY });
              }}
              type="button"
            >
              <Plus size={12} />
            </button>
          ) : null}
        </div>
      </EdgeLabelRenderer>
    </g>
  );
}

export default memo(CustomEdge);
