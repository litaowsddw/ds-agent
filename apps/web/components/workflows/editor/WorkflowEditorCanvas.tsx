"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  BackgroundVariant,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useViewport,
  type EdgeMouseHandler,
  type FinalConnectionState,
  type NodeMouseHandler,
  type OnNodeDrag,
} from "@xyflow/react";
import { MousePointer2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { showToast } from "@/components/layout/AppLayout";
import { nodeTypes } from "@/components/nodes";
import CanvasContextMenu from "@/components/workflows/editor/CanvasContextMenu";
import CanvasOperatorBar from "@/components/workflows/editor/CanvasOperatorBar";
import CustomEdge from "@/components/workflows/editor/CustomEdge";
import NodeQuickAddMenu from "@/components/workflows/editor/NodeQuickAddMenu";
import { NODE_PALETTE, type WorkflowPaletteItem } from "@/lib/constants";
import { useWorkflowStore } from "@/stores/workflow";
import type { CustomNodeData } from "@/types/workflow";
import type { Edge, Node } from "@xyflow/react";

const NODE_DND_MIME = "application/agentflow-node";
const ESTIMATED_NODE_WIDTH = 220;
const ESTIMATED_NODE_HEIGHT = 96;
const SNAP_THRESHOLD = 6;

const edgeTypes = { custom: CustomEdge };

const MINIMAP_COLORS: Record<string, string> = {
  start: "#22c55e",
  end: "#ef4444",
  llm: "#3b82f6",
  rag: "#eab308",
  tool: "#a855f7",
  condition: "#475569",
};

interface QuickAddState {
  /** Anchor (px) inside the canvas wrapper for the menu popup. */
  anchor: { x: number; y: number };
  /** Flow position where the new node should be created. */
  flowPosition: { x: number; y: number };
  /** Pending connection source; undefined when adding standalone. */
  sourceId?: string;
  branch?: "true" | "false";
  /** When set, the new node is inserted into this edge instead. */
  edgeId?: string;
}

interface ContextMenuState {
  kind: "node" | "edge" | "pane";
  id?: string;
  anchor: { x: number; y: number };
  flowPosition: { x: number; y: number };
}

function WorkflowEditorCanvasInner({
  headerLeft,
  headerRight,
}: {
  headerLeft?: React.ReactNode;
  headerRight?: React.ReactNode;
}) {
  const nodes = useWorkflowStore((state) => state.nodes);
  const edges = useWorkflowStore((state) => state.edges);
  const nodeRuns = useWorkflowStore((state) => state.nodeRuns);
  const onNodesChange = useWorkflowStore((state) => state.onNodesChange);
  const onEdgesChange = useWorkflowStore((state) => state.onEdgesChange);
  const onConnect = useWorkflowStore((state) => state.onConnect);
  const validateConnection = useWorkflowStore((state) => state.validateConnection);
  const setSelectedNodeId = useWorkflowStore((state) => state.setSelectedNodeId);
  const setSelectedEdgeId = useWorkflowStore((state) => state.setSelectedEdgeId);
  const addNodeAt = useWorkflowStore((state) => state.addNodeAt);
  const connectNewNode = useWorkflowStore((state) => state.connectNewNode);
  const insertNodeIntoEdge = useWorkflowStore((state) => state.insertNodeIntoEdge);
  const deleteSelection = useWorkflowStore((state) => state.deleteSelection);
  const duplicateSelectedNodes = useWorkflowStore((state) => state.duplicateSelectedNodes);
  const removeSelectedEdge = useWorkflowStore((state) => state.removeSelectedEdge);
  const renameNode = useWorkflowStore((state) => state.renameNode);
  const copySelection = useWorkflowStore((state) => state.copySelection);
  const pasteClipboard = useWorkflowStore((state) => state.pasteClipboard);
  const selectAllNodes = useWorkflowStore((state) => state.selectAllNodes);
  const undo = useWorkflowStore((state) => state.undo);
  const redo = useWorkflowStore((state) => state.redo);
  const applyAutoLayout = useWorkflowStore((state) => state.applyAutoLayout);
  const getWorkflowDraft = useWorkflowStore((state) => state.getWorkflowDraft);
  const setPendingAddPosition = useWorkflowStore((state) => state.setPendingAddPosition);

  const { screenToFlowPosition, flowToScreenPosition } = useReactFlow();
  const viewport = useViewport();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [quickAdd, setQuickAdd] = useState<QuickAddState | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [renamingNodeId, setRenamingNodeId] = useState("");
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [guides, setGuides] = useState<{ vertical: number[]; horizontal: number[] }>({
    vertical: [],
    horizontal: [],
  });

  const runStatusByNode = useMemo(() => {
    const map = new Map<string, string>();
    const ordered = [...nodeRuns].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
    for (const run of ordered) map.set(run.node_id, run.status);
    return map;
  }, [nodeRuns]);

  const toWrapperAnchor = useCallback((clientX: number, clientY: number) => {
    const rect = wrapperRef.current?.getBoundingClientRect();
    return { x: clientX - (rect?.left ?? 0), y: clientY - (rect?.top ?? 0) };
  }, []);

  const openQuickAddFromNode = useCallback(
    (nodeId: string, branch?: "true" | "false") => {
      const node = useWorkflowStore.getState().nodes.find((item) => item.id === nodeId);
      if (!node) return;
      const flowPosition = { x: node.position.x + ESTIMATED_NODE_WIDTH + 80, y: node.position.y - 8 };
      const screen = flowToScreenPosition({
        x: node.position.x + ESTIMATED_NODE_WIDTH + 24,
        y: node.position.y + 28,
      });
      setQuickAdd({
        anchor: toWrapperAnchor(screen.x, screen.y),
        flowPosition,
        sourceId: nodeId,
        branch,
      });
    },
    [flowToScreenPosition, toWrapperAnchor]
  );

  const openInsertIntoEdge = useCallback(
    (edgeId: string, flowPosition: { x: number; y: number }) => {
      const screen = flowToScreenPosition(flowPosition);
      setQuickAdd({
        anchor: toWrapperAnchor(screen.x, screen.y),
        flowPosition: { x: flowPosition.x - ESTIMATED_NODE_WIDTH / 2, y: flowPosition.y - ESTIMATED_NODE_HEIGHT / 2 },
        edgeId,
      });
    },
    [flowToScreenPosition, toWrapperAnchor]
  );

  const derivedNodes = useMemo<Node<CustomNodeData>[]>(
    () =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          runStatus: runStatusByNode.get(node.id),
          onQuickAdd: openQuickAddFromNode,
          renaming: node.id === renamingNodeId,
          onRenameStart: (nodeId: string) => setRenamingNodeId(nodeId),
          onRenameSubmit: (nodeId: string, name: string) => {
            setRenamingNodeId("");
            renameNode(nodeId, name);
          },
        },
      })),
    [nodes, runStatusByNode, openQuickAddFromNode, renamingNodeId, renameNode]
  );

  const derivedEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => ({
        ...edge,
        type: "custom",
        label: undefined,
        data: {
          branch: edge.sourceHandle === "true" || edge.sourceHandle === "false" ? edge.sourceHandle : undefined,
          onInsertNode: openInsertIntoEdge,
        },
      })),
    [edges, openInsertIntoEdge]
  );

  const openMenuAtPointer = useCallback(
    (clientX: number, clientY: number, sourceId?: string, branch?: "true" | "false") => {
      setQuickAdd({
        anchor: toWrapperAnchor(clientX, clientY),
        flowPosition: screenToFlowPosition({ x: clientX, y: clientY }),
        sourceId,
        branch,
      });
    },
    [screenToFlowPosition, toWrapperAnchor]
  );

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData(NODE_DND_MIME);
      const item = NODE_PALETTE.find((entry) => entry.type === type);
      if (!item) return;
      addNodeAt(item, screenToFlowPosition({ x: event.clientX, y: event.clientY }));
    },
    [addNodeAt, screenToFlowPosition]
  );

  const handleDragOver = useCallback(
    (event: React.DragEvent) => {
      if (!event.dataTransfer.types.includes(NODE_DND_MIME)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      setPendingAddPosition(screenToFlowPosition({ x: event.clientX, y: event.clientY }));
    },
    [screenToFlowPosition, setPendingAddPosition]
  );

  const handleConnectEnd = useCallback(
    (event: MouseEvent | TouchEvent, connectionState: FinalConnectionState) => {
      if (connectionState.isValid || !connectionState.fromNode) return;
      const pointer = "changedTouches" in event ? event.changedTouches[0] : event;
      const branch =
        connectionState.fromNode.type === "condition" &&
        (connectionState.fromHandle?.id === "true" || connectionState.fromHandle?.id === "false")
          ? connectionState.fromHandle.id
          : undefined;
      setPendingAddPosition(null);
      openMenuAtPointer(pointer.clientX, pointer.clientY, connectionState.fromNode.id, branch);
    },
    [openMenuAtPointer, setPendingAddPosition]
  );

  const handleQuickAddSelect = useCallback(
    (item: WorkflowPaletteItem) => {
      if (!quickAdd) return;
      if (quickAdd.edgeId) {
        insertNodeIntoEdge(quickAdd.edgeId, item, quickAdd.flowPosition);
      } else if (quickAdd.sourceId) {
        const result = connectNewNode(quickAdd.sourceId, quickAdd.branch, item, quickAdd.flowPosition);
        if (!result.valid) showToast("error", result.message);
      } else {
        addNodeAt(item, quickAdd.flowPosition);
      }
      setQuickAdd(null);
    },
    [addNodeAt, connectNewNode, insertNodeIntoEdge, quickAdd]
  );

  const handleNodeClick: NodeMouseHandler = (_, node) => {
    setSelectedNodeId(node.id);
    setSelectedEdgeId("");
  };

  const handleEdgeClick: EdgeMouseHandler = (_, edge) => {
    setSelectedEdgeId(edge.id);
  };

  const handlePaneClick = useCallback(() => {
    setSelectedNodeId("");
    setSelectedEdgeId("");
    setQuickAdd(null);
    setContextMenu(null);
  }, [setSelectedEdgeId, setSelectedNodeId]);

  const handleDoubleClick = useCallback(
    (event: React.MouseEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest(".react-flow__node") || !target.closest(".react-flow__pane")) return;
      openMenuAtPointer(event.clientX, event.clientY);
    },
    [openMenuAtPointer]
  );

  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      event.preventDefault();
      setSelectedNodeId(node.id);
      setQuickAdd(null);
      setContextMenu({
        kind: "node",
        id: node.id,
        anchor: toWrapperAnchor(event.clientX, event.clientY),
        flowPosition: screenToFlowPosition({ x: event.clientX, y: event.clientY }),
      });
    },
    [screenToFlowPosition, setSelectedNodeId, toWrapperAnchor]
  );

  const handleEdgeContextMenu = useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      event.preventDefault();
      setSelectedEdgeId(edge.id);
      setQuickAdd(null);
      setContextMenu({
        kind: "edge",
        id: edge.id,
        anchor: toWrapperAnchor(event.clientX, event.clientY),
        flowPosition: screenToFlowPosition({ x: event.clientX, y: event.clientY }),
      });
    },
    [screenToFlowPosition, setSelectedEdgeId, toWrapperAnchor]
  );

  const handlePaneContextMenu = useCallback(
    (event: React.MouseEvent | MouseEvent) => {
      event.preventDefault();
      setQuickAdd(null);
      setContextMenu({
        kind: "pane",
        anchor: toWrapperAnchor(event.clientX, event.clientY),
        flowPosition: screenToFlowPosition({ x: event.clientX, y: event.clientY }),
      });
    },
    [screenToFlowPosition, toWrapperAnchor]
  );

  const handleNodeDrag: OnNodeDrag = useCallback(
    (_, dragNode) => {
      const threshold = SNAP_THRESHOLD / viewport.zoom;
      const dragWidth = dragNode.measured?.width ?? ESTIMATED_NODE_WIDTH;
      const dragHeight = dragNode.measured?.height ?? ESTIMATED_NODE_HEIGHT;
      const dragPointsX = [dragNode.position.x, dragNode.position.x + dragWidth / 2, dragNode.position.x + dragWidth];
      const dragPointsY = [dragNode.position.y, dragNode.position.y + dragHeight / 2, dragNode.position.y + dragHeight];

      const snap: { x: { delta: number; line: number } | null; y: { delta: number; line: number } | null } = {
        x: null,
        y: null,
      };
      for (const other of nodes) {
        if (other.id === dragNode.id) continue;
        const otherWidth = other.measured?.width ?? ESTIMATED_NODE_WIDTH;
        const otherHeight = other.measured?.height ?? ESTIMATED_NODE_HEIGHT;
        const otherPointsX = [other.position.x, other.position.x + otherWidth / 2, other.position.x + otherWidth];
        const otherPointsY = [other.position.y, other.position.y + otherHeight / 2, other.position.y + otherHeight];
        dragPointsX.forEach((point, index) => {
          for (const target of otherPointsX) {
            const diff = Math.abs(point - target);
            if (diff < threshold && (!snap.x || diff < Math.abs(snap.x.delta))) {
              snap.x = { delta: target - dragPointsX[index], line: target };
            }
          }
        });
        dragPointsY.forEach((point, index) => {
          for (const target of otherPointsY) {
            const diff = Math.abs(point - target);
            if (diff < threshold && (!snap.y || diff < Math.abs(snap.y.delta))) {
              snap.y = { delta: target - dragPointsY[index], line: target };
            }
          }
        });
      }

      if (snap.x) dragNode.position.x += snap.x.delta;
      if (snap.y) dragNode.position.y += snap.y.delta;
      setGuides({
        vertical: snap.x ? [snap.x.line] : [],
        horizontal: snap.y ? [snap.y.line] : [],
      });
    },
    [nodes, viewport.zoom]
  );

  const handleNodeDragStop: OnNodeDrag = useCallback(() => {
    setGuides({ vertical: [], horizontal: [] });
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable=true]")) return;
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        deleteSelection();
      } else if (mod && key === "z" && !event.shiftKey) {
        event.preventDefault();
        undo();
      } else if (mod && (key === "y" || (key === "z" && event.shiftKey))) {
        event.preventDefault();
        redo();
      } else if (mod && key === "d") {
        event.preventDefault();
        const count = duplicateSelectedNodes();
        if (count > 0) showToast("success", `已复制 ${count} 个节点`);
      } else if (mod && key === "c") {
        const count = copySelection();
        if (count > 0) {
          event.preventDefault();
          showToast("success", `已复制 ${count} 个节点到剪贴板`);
        }
      } else if (mod && key === "v") {
        const count = pasteClipboard();
        if (count > 0) {
          event.preventDefault();
          showToast("success", `已粘贴 ${count} 个节点`);
        }
      } else if (mod && key === "a") {
        event.preventDefault();
        selectAllNodes();
      } else if (event.key === "Escape") {
        setQuickAdd(null);
        setContextMenu(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [copySelection, deleteSelection, duplicateSelectedNodes, pasteClipboard, redo, selectAllNodes, undo]);

  const contextMenuItems = useMemo(() => {
    if (!contextMenu) return [];
    if (contextMenu.kind === "node") {
      return [
        { label: "重命名", onSelect: () => setRenamingNodeId(contextMenu.id ?? "") },
        { label: "复制", onSelect: () => void duplicateSelectedNodes() },
        { label: "删除", danger: true, onSelect: () => deleteSelection() },
      ];
    }
    if (contextMenu.kind === "edge") {
      return [{ label: "删除连线", danger: true, onSelect: () => removeSelectedEdge() }];
    }
    return [
      {
        label: "在此添加节点",
        onSelect: () =>
          setQuickAdd({
            anchor: contextMenu.anchor,
            flowPosition: contextMenu.flowPosition,
          }),
      },
      { label: "粘贴节点", onSelect: () => void pasteClipboard(contextMenu.flowPosition) },
      { label: "全选", onSelect: () => selectAllNodes() },
      { label: "自动布局", onSelect: () => applyAutoLayout() },
      {
        label: "复制 DSL (JSON)",
        onSelect: () => {
          try {
            void navigator.clipboard.writeText(JSON.stringify(getWorkflowDraft(), null, 2));
            showToast("success", "DSL 已复制到剪贴板");
          } catch (error) {
            showToast("error", error instanceof Error ? error.message : "复制失败");
          }
        },
      },
    ];
  }, [applyAutoLayout, contextMenu, deleteSelection, duplicateSelectedNodes, getWorkflowDraft, pasteClipboard, removeSelectedEdge, selectAllNodes]);

  const hasRunStatuses = runStatusByNode.size > 0;

  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-[#dfe4ee] px-4 py-2.5">
        <div className="min-w-0">{headerLeft}</div>
        <div className="flex shrink-0 items-center gap-2">{headerRight}</div>
      </div>

      <div
        className="relative min-h-0 flex-1 bg-[#f7f8fa]"
        onDoubleClick={handleDoubleClick}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        ref={wrapperRef}
      >
        <ReactFlow
          connectionLineStyle={{ stroke: "#2f6feb", strokeWidth: 2 }}
          defaultEdgeOptions={{ type: "custom" }}
          deleteKeyCode={null}
          edgeTypes={edgeTypes}
          edges={derivedEdges}
          fitView
          fitViewOptions={{ padding: 0.22 }}
          isValidConnection={(connection) =>
            validateConnection(
              connection.source,
              connection.target,
              connection.sourceHandle === "true" || connection.sourceHandle === "false"
                ? connection.sourceHandle
                : undefined
            ).valid
          }
          nodeTypes={nodeTypes}
          nodes={derivedNodes}
          onConnect={onConnect}
          onConnectEnd={handleConnectEnd}
          onEdgeClick={handleEdgeClick}
          onEdgeContextMenu={handleEdgeContextMenu}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          onNodeContextMenu={handleNodeContextMenu}
          onNodeDrag={handleNodeDrag}
          onNodeDragStop={handleNodeDragStop}
          onNodesChange={onNodesChange}
          onPaneClick={handlePaneClick}
          onPaneContextMenu={handlePaneContextMenu}
          panOnScroll
          selectionOnDrag
          snapGrid={[20, 20]}
          snapToGrid={snapEnabled}
        >
          <Background color="#d9e0ec" gap={18} variant={BackgroundVariant.Dots} />
          <MiniMap
            className="!rounded-lg !border !border-[#dfe4ee] !shadow-sm"
            nodeColor={(node) => MINIMAP_COLORS[String(node.type ?? "")] ?? "#94a3b8"}
            nodeStrokeWidth={3}
            pannable
            position="bottom-right"
            zoomable
          />
        </ReactFlow>

        {guides.vertical.map((line) => (
          <div
            className="pointer-events-none absolute bottom-0 top-0 w-px bg-[#f04438]"
            key={`v-${line}`}
            style={{ left: line * viewport.zoom + viewport.x }}
          />
        ))}
        {guides.horizontal.map((line) => (
          <div
            className="pointer-events-none absolute left-0 right-0 h-px bg-[#f04438]"
            key={`h-${line}`}
            style={{ top: line * viewport.zoom + viewport.y }}
          />
        ))}

        <CanvasOperatorBar snapEnabled={snapEnabled} onToggleSnap={() => setSnapEnabled((value) => !value)} />

        {quickAdd ? (
          <NodeQuickAddMenu
            anchor={quickAdd.anchor}
            onClose={() => setQuickAdd(null)}
            onSelect={handleQuickAddSelect}
          />
        ) : null}

        {contextMenu ? (
          <CanvasContextMenu
            anchor={contextMenu.anchor}
            items={contextMenuItems}
            onClose={() => setContextMenu(null)}
          />
        ) : null}

        <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 rounded-lg border border-[#dfe4ee] bg-white/90 px-3 py-2 text-xs text-[#667085] shadow-sm">
          <MousePointer2 size={14} />
          拖入节点 · 拖线到空白快速添加 · 悬停连线中点插入节点 · 右键更多操作
        </div>

        {hasRunStatuses ? (
          <div className="pointer-events-none absolute right-4 top-4 space-x-2 rounded-lg border border-[#dfe4ee] bg-white/90 px-3 py-2 text-xs text-[#667085] shadow-sm">
            <span className="font-medium text-[#344054]">运行状态</span>
            <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[#12b76a]" />成功</span>
            <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[#f04438]" />失败</span>
            <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-[#cbd5e1]" />跳过/待执行</span>
          </div>
        ) : null}
      </div>
    </>
  );
}

export default function WorkflowEditorCanvas(props: {
  headerLeft?: React.ReactNode;
  headerRight?: React.ReactNode;
}) {
  return (
    <ReactFlowProvider>
      <WorkflowEditorCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
