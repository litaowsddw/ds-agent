/** LLM 节点 - 模型推理节点。

带有 Bot 图标的蓝色 LLM 推理节点。
 */

"use client";

import { memo } from "react";
import { type NodeProps, Handle, Position } from "@xyflow/react";
import { Bot } from "lucide-react";

function LLMNode({ data }: NodeProps) {
  return (
    <div className="min-w-[150px] rounded-xl border-2 border-[#93c5fd] bg-[#eef4ff] px-4 py-3 shadow-sm transition-shadow hover:shadow-md">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
      />
      <div className="flex items-center gap-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-[#3b82f6] text-white">
          <Bot size={18} />
        </div>
        <div>
          <div className="text-sm font-semibold text-[#1e40af]">LLM</div>
          <div className="text-xs text-[#667085]">模型推理</div>
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

export default memo(LLMNode);
