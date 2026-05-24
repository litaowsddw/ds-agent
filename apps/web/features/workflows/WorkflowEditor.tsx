"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node
} from "@xyflow/react";
import { Bot, CircleDot, Play, Save, Workflow } from "lucide-react";
import { useMemo, useState } from "react";

// initialNodes 是 MVP 工作流编辑器的默认节点，覆盖 Start -> LLM -> End 主链路。
const initialNodes: Node[] = [
  {
    id: "start",
    type: "default",
    position: { x: 80, y: 160 },
    data: { label: "Start" }
  },
  {
    id: "llm",
    type: "default",
    position: { x: 360, y: 160 },
    data: { label: "LLM" }
  },
  {
    id: "end",
    type: "default",
    position: { x: 640, y: 160 },
    data: { label: "End" }
  }
];

// initialEdges 是默认连线，确保页面第一次打开就是可发布的最小工作流。
const initialEdges: Edge[] = [
  { id: "start-llm", source: "start", target: "llm" },
  { id: "llm-end", source: "llm", target: "end" }
];

export default function WorkflowEditor() {
  // nodes 保存画布节点状态。
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);

  // edges 保存画布连线状态。
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // selectedNodeId 保存当前选中节点 ID，用于右侧属性面板展示。
  const [selectedNodeId, setSelectedNodeId] = useState<string>("llm");

  // workflowDraft 是当前画布生成的后端 DSL 草稿。
  const workflowDraft = useMemo(() => {
    return {
      version: "1.0",
      nodes: nodes.map((node) => ({
        id: node.id,
        type: String(node.data.label).toLowerCase(),
        config: {
          label: node.data.label
        }
      })),
      edges: edges.map((edge) => ({
        source: edge.source,
        target: edge.target
      }))
    };
  }, [nodes, edges]);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId);

  function handleConnect(connection: Connection) {
    // 新连线写入 edges；React Flow 会负责校验 source/target 的基本结构。
    setEdges((currentEdges) => addEdge(connection, currentEdges));
  }

  function addLlmNode() {
    // nodeIndex 用于生成稳定且不冲突的新节点 ID。
    const nodeIndex = nodes.length + 1;
    setNodes((currentNodes) => [
      ...currentNodes,
      {
        id: `llm_${nodeIndex}`,
        type: "default",
        position: { x: 320 + nodeIndex * 24, y: 280 },
        data: { label: "LLM" }
      }
    ]);
  }

  return (
    <main className="grid min-h-screen grid-cols-[280px_1fr_360px] bg-canvas text-ink">
      <aside className="border-r border-line bg-panel p-4">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded bg-accent text-white">
            <Workflow size={18} />
          </div>
          <div>
            <h1 className="text-base font-semibold">Workflow</h1>
            <p className="text-xs text-muted">可视化草稿编辑器</p>
          </div>
        </div>

        <div className="space-y-2">
          <button
            className="flex w-full items-center gap-2 rounded border border-line bg-white px-3 py-2 text-sm"
            onClick={addLlmNode}
            type="button"
          >
            <Bot size={16} />
            添加 LLM 节点
          </button>
          <button
            className="flex w-full items-center gap-2 rounded border border-line bg-white px-3 py-2 text-sm"
            type="button"
          >
            <Save size={16} />
            保存草稿
          </button>
          <button
            className="flex w-full items-center gap-2 rounded border border-line bg-accent px-3 py-2 text-sm text-white"
            type="button"
          >
            <Play size={16} />
            发布版本
          </button>
        </div>
      </aside>

      <section className="h-screen">
        <ReactFlow
          edges={edges}
          fitView
          nodes={nodes}
          onConnect={handleConnect}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => setSelectedNodeId(node.id)}
          onNodesChange={onNodesChange}
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </section>

      <aside className="border-l border-line bg-panel p-4">
        <div className="mb-5 flex items-center gap-2">
          <CircleDot size={17} className="text-accent" />
          <h2 className="text-sm font-semibold">节点属性</h2>
        </div>

        <div className="mb-6 space-y-3 border-b border-line pb-5">
          <div>
            <label className="mb-1 block text-xs text-muted">节点 ID</label>
            <div className="rounded border border-line bg-canvas px-3 py-2 text-sm">
              {selectedNode?.id ?? "未选择"}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">节点类型</label>
            <div className="rounded border border-line bg-canvas px-3 py-2 text-sm">
              {selectedNode?.data.label ? String(selectedNode.data.label) : "未选择"}
            </div>
          </div>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold">草稿 DSL</h3>
          <pre className="max-h-[520px] overflow-auto rounded border border-line bg-canvas p-3 text-xs leading-5">
            {JSON.stringify(workflowDraft, null, 2)}
          </pre>
        </div>
      </aside>
    </main>
  );
}

