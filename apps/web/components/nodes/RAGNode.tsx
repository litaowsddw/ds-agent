/** RAG 节点 - 知识检索节点。

带有数据库图标的黄色 RAG 检索节点。
 */

"use client";

import { memo } from "react";
import { type NodeProps, Handle, Position } from "@xyflow/react";
import { Database } from "lucide-react";

function RAGNode({ data }: NodeProps) {
  return (
    <div className="min-w-[150px] rounded-xl border-2 border-[#fde047] bg-[#fefce8] px-4 py-3 shadow-sm transition-shadow hover:shadow-md">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !rounded-full !border-2 !border-white !bg-[#94a3b8]"
      />
      <div className="flex items-center gap-2">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-[#eab308] text-white">
          <Database size={18} />
        </div>
        <div>
          <div className="text-sm font-semibold text-[#854d0e]">RAG</div>
          <div className="text-xs text-[#667085]">知识检索</div>
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

export default memo(RAGNode);
