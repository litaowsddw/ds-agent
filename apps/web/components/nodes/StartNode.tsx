/** Start 节点 - 工作流起始节点。

绿色起始节点，只有输出手柄。
 */

"use client";

import { memo } from "react";
import { type NodeProps, Handle, Position } from "@xyflow/react";
import { Play } from "lucide-react";

function StartNode({ data }: NodeProps) {
  return (
    <div className="min-w-[120px] rounded-xl border-2 border-[#86efac] bg-[#f0fdf4] px-4 py-3 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-center gap-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-[#22c55e] text-white">
          <Play size={18} />
        </div>
        <div>
          <div className="text-sm font-semibold text-[#166534]">Start</div>
          <div className="text-xs text-[#667085]">输入</div>
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

export default memo(StartNode);
