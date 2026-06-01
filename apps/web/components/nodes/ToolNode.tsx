/** Tool 节点 - 工具调用节点。

带有盾牌图标的紫色工具调用节点。
 */

"use client";

import { memo } from "react";
import { type NodeProps, Handle, Position } from "@xyflow/react";
import { ShieldCheck } from "lucide-react";

function ToolNode({ data }: NodeProps) {
  return (
    <div className="min-w-[150px] rounded-xl border-2 border-[#d8b4fe] bg-[#faf5ff] px-4 py-3 shadow-sm transition-shadow hover:shadow-md">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
      />
      <div className="flex items-center gap-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-[#a855f7] text-white">
          <ShieldCheck size={18} />
        </div>
        <div>
          <div className="text-sm font-semibold text-[#6b21a8]">Tool</div>
          <div className="text-xs text-[#667085]">工具调用</div>
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
      />
    </div>
  );
}

export default memo(ToolNode);
