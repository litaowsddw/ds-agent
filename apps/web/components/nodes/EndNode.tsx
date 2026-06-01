/** End 节点 - 工作流终止节点。

红色终止节点，只有输入手柄。
 */

"use client";

import { memo } from "react";
import { type NodeProps, Handle, Position } from "@xyflow/react";
import { CheckCircle2 } from "lucide-react";

function EndNode({ data }: NodeProps) {
  return (
    <div className="min-w-[120px] rounded-xl border-2 border-[#fca5a5] bg-[#fef2f2] px-4 py-3 shadow-sm transition-shadow hover:shadow-md">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
      />
      <div className="flex items-center gap-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-[#ef4444] text-white">
          <CheckCircle2 size={18} />
        </div>
        <div>
          <div className="text-sm font-semibold text-[#991b1b]">End</div>
          <div className="text-xs text-[#667085]">输出</div>
        </div>
      </div>
    </div>
  );
}

export default memo(EndNode);
