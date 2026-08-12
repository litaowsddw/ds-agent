/** Workflow state management. */

import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import { create } from "zustand";
import { cloneWorkflowDefinition } from "@/components/workflows/workflowTemplates";
import { apiRequest } from "@/lib/api";
import { INITIAL_EDGES, INITIAL_NODES, type WorkflowPaletteItem } from "@/lib/constants";
import { useKnowledgeStore } from "@/stores/knowledge";
import { useRuntimeStore } from "@/stores/runtime";
import type {
  CustomNodeData,
  NodeRun,
  WorkflowDefinition,
  WorkflowExecutionLimits,
  WorkflowItem,
  WorkflowRun,
  WorkflowTemplate,
  WorkflowValidationResult,
  WorkflowVersion,
} from "@/types/workflow";

type ConditionBranch = "true" | "false";
export type EditableExecutionLimits = { max_steps: string; max_llm_calls: string };

interface CanvasSnapshot {
  nodes: Node<CustomNodeData>[];
  edges: Edge[];
}

interface CanvasHistory {
  past: CanvasSnapshot[];
  future: CanvasSnapshot[];
}

const HISTORY_LIMIT = 80;
const PROTECTED_NODE_TYPES = new Set(["start", "end"]);

function takeSnapshot(nodes: Node<CustomNodeData>[], edges: Edge[]): CanvasSnapshot {
  return {
    nodes: nodes.map((node) => ({
      ...node,
      position: { ...node.position },
      data: {
        ...node.data,
        config: node.data.config ? { ...node.data.config } : node.data.config,
      },
    })),
    edges: edges.map((edge) => ({ ...edge })),
  };
}

function pushHistory(history: CanvasHistory, nodes: Node<CustomNodeData>[], edges: Edge[]): CanvasHistory {
  return {
    past: [...history.past.slice(-(HISTORY_LIMIT - 1)), takeSnapshot(nodes, edges)],
    future: [],
  };
}

/** Node ids currently being dragged; one history snapshot per drag gesture. */
const dragSnapshotIds = new Set<string>();

interface WorkflowStore {
  nodes: Node<CustomNodeData>[];
  edges: Edge[];
  workflows: WorkflowItem[];
  selectedWorkflowId: string;
  selectedNodeId: string;
  selectedEdgeId: string;
  versions: WorkflowVersion[];
  runs: WorkflowRun[];
  selectedRunId: string;
  nodeRuns: NodeRun[];
  workflowForm: { name: string; description: string; input: string };
  executionLimits: EditableExecutionLimits;
  validation: WorkflowValidationResult | null;
  history: CanvasHistory;
  /** Flow position where a palette click should drop a node (tracks canvas pointer). */
  pendingAddPosition: { x: number; y: number } | null;

  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  validateConnection: (
    sourceId: string | null | undefined,
    targetId: string | null | undefined,
    branch?: ConditionBranch
  ) => WorkflowConnectionResult;
  connectNodes: (sourceId: string, targetId: string, branch?: ConditionBranch) => WorkflowConnectionResult;
  addNode: (item: WorkflowPaletteItem) => void;
  addNodeAt: (item: WorkflowPaletteItem, position: { x: number; y: number }) => void;
  /** Creates a node at `position` and wires it to `sourceId` in one undo step. */
  connectNewNode: (
    sourceId: string | null,
    branch: ConditionBranch | undefined,
    item: WorkflowPaletteItem,
    position: { x: number; y: number }
  ) => WorkflowConnectionResult;
  /** Splits an existing edge and inserts a new node between its ends. */
  insertNodeIntoEdge: (
    edgeId: string,
    item: WorkflowPaletteItem,
    position: { x: number; y: number }
  ) => boolean;
  /** Renames a node's display name (empty string restores the type default). */
  renameNode: (nodeId: string, displayName: string) => void;
  /** Copies selected non-protected nodes to the clipboard; returns the count. */
  copySelection: () => number;
  /** Pastes clipboard nodes at an optional position; returns the count. */
  pasteClipboard: (position?: { x: number; y: number }) => number;
  selectAllNodes: () => void;
  duplicateSelectedNodes: () => number;
  deleteSelection: () => void;
  removeSelectedNode: () => void;
  removeSelectedEdge: () => void;
  undo: () => void;
  redo: () => void;
  applyAutoLayout: () => void;
  setPendingAddPosition: (position: { x: number; y: number } | null) => void;
  setSelectedNodeId: (id: string) => void;
  setSelectedEdgeId: (id: string) => void;
  updateSelectedNodeConfig: (patch: Record<string, unknown>) => void;
  setWorkflowForm: (form: { name: string; description: string; input: string }) => void;
  setExecutionLimits: (limits: EditableExecutionLimits) => void;
  applyWorkflowTemplate: (template: WorkflowTemplate) => void;
  setSelectedWorkflowId: (id: string) => void;
  setSelectedRunId: (id: string) => void;
  resetCanvas: () => void;
  getWorkflowDraft: () => WorkflowDefinition;
  createWorkflow: (actorUserId: string, agentId: string) => Promise<void>;
  saveWorkflowDraft: (actorUserId: string) => Promise<void>;
  validateWorkflow: (actorUserId: string) => Promise<WorkflowValidationResult>;
  publishWorkflow: (actorUserId: string) => Promise<void>;
  refreshVersions: (workflowIds: string[], actorUserId: string) => Promise<void>;
  restoreVersionToDraft: (actorUserId: string, versionId: string) => Promise<void>;
  runWorkflow: (actorUserId: string, input: string) => Promise<void>;
  loadNodeRuns: (runId: string, actorUserId: string) => Promise<void>;
  clearRunSelection: () => void;
  resetWorkspaceData: () => void;
  refreshWorkflows: (orgId: string, actorUserId: string, agentId?: string) => Promise<void>;
  refreshRuns: (orgId: string, actorUserId: string) => Promise<void>;
}

export interface WorkflowConnectionResult {
  valid: boolean;
  message: string;
}

const NODE_META: Record<string, { label: string; description: string; capability: "executable" | "schema" }> = {
  start: { label: "Start", description: "Workflow input", capability: "executable" },
  end: { label: "End", description: "Workflow result", capability: "executable" },
  llm: { label: "LLM", description: "Model call", capability: "executable" },
  rag: { label: "Knowledge Retrieval", description: "Vector knowledge search", capability: "executable" },
  tool: { label: "Tool", description: "Authorized MCP tool plan", capability: "executable" },
  condition: { label: "Condition", description: "Route by a safe data check", capability: "executable" },
  http: { label: "HTTP Request", description: "External HTTP call", capability: "schema" },
  code: { label: "Code", description: "Sandboxed transform", capability: "schema" },
  variable: { label: "Variable", description: "Assign workflow values", capability: "schema" },
  template: { label: "Template", description: "Render text", capability: "schema" },
  human: { label: "Human Approval", description: "Manual approval step", capability: "schema" },
};

function defaultConfig(type: string): Record<string, unknown> {
  switch (type) {
    case "llm":
      return {
        provider: "",
        model: "",
        system_prompt: "",
        prompt: "",
        temperature: 0,
        max_tokens: 512,
      };
    case "rag":
      return { kb_id: "", query_template: "{{input.text}}", limit: 5 };
    case "tool":
      return { tool_id: "", risk_level: "low", arguments: { query: "{{input.text}}" } };
    case "condition":
      return { left: "{{input.status}}", operator: "equals", value: "ok", value_type: "string" };
    case "http":
      return { method: "GET", url: "", headers: {}, body: "" };
    case "code":
      return { language: "python", code: "def main(input):\n    return input" };
    case "variable":
      return { name: "value", value: "{{input.text}}" };
    case "template":
      return { template: "{{input.text}}" };
    case "human":
      return { title: "Review required", instructions: "" };
    default:
      return {};
  }
}

function makeNode(
  type: string,
  id: string,
  position: { x: number; y: number },
  config?: Record<string, unknown>
): Node<CustomNodeData> {
  const meta = NODE_META[type] ?? { label: type, description: "Custom node", capability: "schema" as const };
  const mergedConfig = { ...defaultConfig(type), ...(config ?? {}) };
  if (
    type === "condition" &&
    config &&
    !Object.prototype.hasOwnProperty.call(config, "value_type") &&
    Object.prototype.hasOwnProperty.call(mergedConfig, "value")
  ) {
    mergedConfig.value_type = conditionValueType(mergedConfig.value);
  }
  return {
    id,
    type,
    position,
    data: {
      label: meta.label,
      description: meta.description,
      capability: meta.capability,
      config: mergedConfig,
    },
  };
}

function cleanConfig(config: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(config).filter(([, value]) => value !== undefined && value !== "")
  );
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function hydrateNodes(definition: WorkflowDefinition): Node<CustomNodeData>[] {
  return definition.nodes.map((node, index) => {
    const savedPosition = node.position;
    const position =
      savedPosition && Number.isFinite(savedPosition.x) && Number.isFinite(savedPosition.y)
        ? { x: savedPosition.x, y: savedPosition.y }
        : { x: 80 + index * 300, y: 260 };
    return makeNode(node.type, node.id, position, node.config);
  });
}

function hydrateEdges(definition: WorkflowDefinition): Edge[] {
  return definition.edges.map((edge, index) => ({
    id: `${edge.source}-${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.branch,
    label: edge.branch,
    labelStyle: edge.branch ? { fill: "#475467", fontSize: 11, fontWeight: 600 } : undefined,
  }));
}

function conditionValueType(value: unknown): "string" | "number" | "boolean" | "null" {
  if (value === null) return "null";
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  return "string";
}

function coerceConditionValue(value: unknown, valueType: unknown): string | number | boolean | null {
  switch (valueType) {
    case "number": {
      const numeric = typeof value === "number" ? value : Number(value);
      return Number.isFinite(numeric) ? numeric : 0;
    }
    case "boolean":
      return value === true || value === "true";
    case "null":
      return null;
    default:
      return typeof value === "string" ? value : String(value ?? "");
  }
}

function editableExecutionLimits(definition: WorkflowDefinition): EditableExecutionLimits {
  const limits = definition.execution_limits;
  return {
    max_steps: limits?.max_steps === undefined ? "" : String(limits.max_steps),
    max_llm_calls: limits?.max_llm_calls === undefined ? "" : String(limits.max_llm_calls),
  };
}

function parseExecutionLimit(value: string, name: "max_steps" | "max_llm_calls"): number | undefined {
  const text = value.trim();
  if (!text) return undefined;
  if (!/^\d+$/.test(text)) {
    throw new Error(`${name} must be a whole number`);
  }
  const parsed = Number(text);
  const [minimum, maximum] = name === "max_steps" ? [1, 500] : [0, 100];
  if (parsed < minimum || parsed > maximum) {
    throw new Error(`${name} must be between ${minimum} and ${maximum}`);
  }
  return parsed;
}

function serializeExecutionLimits(limits: EditableExecutionLimits): WorkflowExecutionLimits | undefined {
  const maxSteps = parseExecutionLimit(limits.max_steps, "max_steps");
  const maxLlmCalls = parseExecutionLimit(limits.max_llm_calls, "max_llm_calls");
  if (maxSteps === undefined && maxLlmCalls === undefined) return undefined;
  return {
    ...(maxSteps === undefined ? {} : { max_steps: maxSteps }),
    ...(maxLlmCalls === undefined ? {} : { max_llm_calls: maxLlmCalls }),
  };
}

function wouldCreateCycle(edges: Edge[], sourceId: string, targetId: string): boolean {
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    const targets = adjacency.get(edge.source) ?? [];
    targets.push(edge.target);
    adjacency.set(edge.source, targets);
  }

  const pending = [targetId];
  const visited = new Set<string>();
  while (pending.length > 0) {
    const current = pending.pop() as string;
    if (current === sourceId) return true;
    if (visited.has(current)) continue;
    visited.add(current);
    pending.push(...(adjacency.get(current) ?? []));
  }
  return false;
}

/** Guards around the ids the canvas must never remove. */
function isProtectedNode(node: Node<CustomNodeData> | undefined, nodeId?: string): boolean {
  if (node) return PROTECTED_NODE_TYPES.has(String(node.type ?? ""));
  return nodeId === "start" || nodeId === "end";
}

/** Computes a layered DAG layout. Layers come from BFS depth off the start node. */
export function computeAutoLayoutPositions(
  nodes: Node<CustomNodeData>[],
  edges: Edge[]
): Map<string, { x: number; y: number }> {
  const LAYER_WIDTH = 320;
  const ROW_HEIGHT = 150;
  const layerById = new Map<string, number>();
  const startNode = nodes.find((node) => node.type === "start") ?? nodes[0];
  if (startNode) {
    layerById.set(startNode.id, 0);
    const queue = [startNode.id];
    // A cyclic draft (legacy data) must not spin forever: stop once every
    // reachable node settled at its deepest layer, at most |nodes| passes.
    let remainingPasses = nodes.length + 1;
    while (queue.length > 0 && remainingPasses > 0) {
      remainingPasses -= 1;
      const current = queue.shift() as string;
      const currentLayer = layerById.get(current) ?? 0;
      for (const edge of edges) {
        if (edge.source !== current) continue;
        const nextLayer = currentLayer + 1;
        if (nextLayer > nodes.length) continue;
        if (!layerById.has(edge.target) || (layerById.get(edge.target) ?? 0) < nextLayer) {
          layerById.set(edge.target, nextLayer);
          queue.push(edge.target);
        }
      }
    }
  }
  // Nodes unreachable from start are appended after the deepest known layer.
  const orphanLayer = 1 + Math.max(0, ...layerById.values());
  const grouped = new Map<number, string[]>();
  for (const node of nodes) {
    const layer = layerById.get(node.id) ?? orphanLayer;
    grouped.set(layer, [...(grouped.get(layer) ?? []), node.id]);
  }
  const positions = new Map<string, { x: number; y: number }>();
  for (const [layer, ids] of grouped) {
    ids.forEach((id, index) => {
      positions.set(id, {
        x: 120 + layer * LAYER_WIDTH,
        y: 300 - (ids.length - 1) * (ROW_HEIGHT / 2) + index * ROW_HEIGHT,
      });
    });
  }
  return positions;
}

function checkConnection(
  nodes: Node<CustomNodeData>[],
  edges: Edge[],
  sourceId: string | null | undefined,
  targetId: string | null | undefined,
  branch?: ConditionBranch
): WorkflowConnectionResult {
  if (!sourceId || !targetId) {
    return { valid: false, message: "Choose both a source and a target step" };
  }
  if (sourceId === targetId) {
    return { valid: false, message: "A step cannot connect to itself" };
  }
  const source = nodes.find((node) => node.id === sourceId);
  const target = nodes.find((node) => node.id === targetId);
  if (!source || !target) {
    return { valid: false, message: "The selected step is no longer on the canvas" };
  }
  if (source.type === "end") {
    return { valid: false, message: "End cannot have an outgoing connection" };
  }
  if (target.type === "start") {
    return { valid: false, message: "Start cannot have an incoming connection" };
  }
  const sourceIsCondition = source.type === "condition";
  if (sourceIsCondition && branch !== "true" && branch !== "false") {
    return { valid: false, message: "Choose the true or false output for this Condition" };
  }
  if (!sourceIsCondition && branch) {
    return { valid: false, message: "Only a Condition can have a named output branch" };
  }
  if (sourceIsCondition && edges.some((edge) => edge.source === sourceId && edge.sourceHandle === branch)) {
    return { valid: false, message: `The ${branch} branch is already connected` };
  }
  if (!sourceIsCondition && edges.some((edge) => edge.source === sourceId && edge.target === targetId)) {
    return { valid: false, message: "This connection already exists" };
  }
  if (wouldCreateCycle(edges, sourceId, targetId)) {
    return { valid: false, message: "This connection would create a cycle" };
  }
  return { valid: true, message: "Connection is valid" };
}

export const useWorkflowStore = create<WorkflowStore>((set, get) => ({
  nodes: INITIAL_NODES as Node<CustomNodeData>[],
  edges: INITIAL_EDGES as Edge[],
  workflows: [],
  selectedWorkflowId: "",
  selectedNodeId: "llm",
  selectedEdgeId: "",
  versions: [],
  runs: [],
  selectedRunId: "",
  nodeRuns: [],
  workflowForm: { name: "", description: "", input: "" },
  executionLimits: { max_steps: "", max_llm_calls: "" },
  validation: null,
  history: { past: [], future: [] },
  pendingAddPosition: null,

  onNodesChange: (changes) => {
    const nodesById = new Map(get().nodes.map((node) => [node.id, node]));
    const allowedChanges = changes.filter((change) => {
      if (change.type !== "remove") return true;
      return !isProtectedNode(nodesById.get(change.id), change.id);
    });
    if (allowedChanges.length === 0) return;

    const hasRemoval = allowedChanges.some((change) => change.type === "remove");
    let dragStarted = false;
    for (const change of allowedChanges) {
      if (change.type === "position" && change.dragging && !dragSnapshotIds.has(change.id)) {
        dragSnapshotIds.add(change.id);
        dragStarted = true;
      } else if (change.type === "position" && change.dragging === false) {
        dragSnapshotIds.delete(change.id);
      }
    }

    set((state) => ({
      nodes: applyNodeChanges(allowedChanges, state.nodes) as Node<CustomNodeData>[],
      validation: null,
      history: hasRemoval || dragStarted ? pushHistory(state.history, state.nodes, state.edges) : state.history,
      selectedNodeId: allowedChanges.some(
        (change) => change.type === "remove" && change.id === state.selectedNodeId
      )
        ? ""
        : state.selectedNodeId,
    }));
  },
  onEdgesChange: (changes) => {
    const hasRemoval = changes.some((change) => change.type === "remove");
    set((state) => ({
      edges: applyEdgeChanges(changes, state.edges),
      validation: null,
      history: hasRemoval ? pushHistory(state.history, state.nodes, state.edges) : state.history,
      selectedEdgeId: changes.some((change) => change.type === "remove" && change.id === state.selectedEdgeId)
        ? ""
        : state.selectedEdgeId,
    }));
  },
  validateConnection: (sourceId, targetId, branch) =>
    checkConnection(get().nodes, get().edges, sourceId, targetId, branch),

  connectNodes: (sourceId, targetId, branch) => {
    const result = get().validateConnection(sourceId, targetId, branch);
    if (!result.valid) return result;

    set((state) => ({
      history: pushHistory(state.history, state.nodes, state.edges),
      edges: addEdge(
        {
          id: `${sourceId}-${targetId}-${Date.now().toString(36)}`,
          source: sourceId,
          target: targetId,
          sourceHandle: branch,
          label: branch,
          labelStyle: branch ? { fill: "#475467", fontSize: 11, fontWeight: 600 } : undefined,
          animated: true,
        },
        state.edges
      ),
      selectedEdgeId: "",
      validation: null,
    }));
    return result;
  },

  onConnect: (connection) => {
    if (!connection.source || !connection.target) return;
    const source = get().nodes.find((node) => node.id === connection.source);
    const branch = source?.type === "condition" && (connection.sourceHandle === "true" || connection.sourceHandle === "false")
      ? connection.sourceHandle
      : undefined;
    get().connectNodes(connection.source, connection.target, branch);
  },

  addNode: (item) => {
    const state = get();
    const anchor =
      state.nodes.find((node) => node.id === state.selectedNodeId) ??
      state.nodes.find((node) => node.type === "end") ??
      state.nodes[state.nodes.length - 1];
    const fallback = anchor
      ? { x: anchor.position.x + 40, y: anchor.position.y + 160 }
      : { x: 260 + state.nodes.length * 24, y: 140 + state.nodes.length * 16 };
    get().addNodeAt(item, state.pendingAddPosition ?? fallback);
  },

  addNodeAt: (item, position) => {
    const nodeIndex = get().nodes.length + 1;
    const id = `${item.type}_${Date.now().toString(36)}_${nodeIndex}`;
    set((state) => ({
      history: pushHistory(state.history, state.nodes, state.edges),
      nodes: [...state.nodes, makeNode(item.type, id, position)],
      selectedNodeId: id,
      selectedEdgeId: "",
      validation: null,
    }));
  },

  connectNewNode: (sourceId, branch, item, position) => {
    const state = get();
    const nodeIndex = state.nodes.length + 1;
    const timestamp = Date.now().toString(36);
    const id = `${item.type}_${timestamp}_${nodeIndex}`;
    const candidate = makeNode(item.type, id, position);
    if (sourceId) {
      // The node does not exist yet, so validate against a hypothetical canvas.
      const check = checkConnection([...state.nodes, candidate], state.edges, sourceId, id, branch);
      if (!check.valid) return check;
    }
    const branchLabelStyle = branch ? { fill: "#475467", fontSize: 11, fontWeight: 600 } : undefined;
    set((current) => ({
      history: pushHistory(current.history, current.nodes, current.edges),
      nodes: [...current.nodes, candidate],
      edges: sourceId
        ? [
            ...current.edges,
            {
              id: `${sourceId}-${id}-${timestamp}`,
              source: sourceId,
              target: id,
              sourceHandle: branch,
              label: branch,
              labelStyle: branchLabelStyle,
              animated: true,
            },
          ]
        : current.edges,
      selectedNodeId: id,
      selectedEdgeId: "",
      validation: null,
    }));
    return { valid: true, message: "Connection is valid" };
  },

  duplicateSelectedNodes: () => {
    const state = get();
    const candidates = state.nodes.filter(
      (node) => (node.selected || node.id === state.selectedNodeId) && !isProtectedNode(node)
    );
    if (candidates.length === 0) return 0;
    const timestamp = Date.now().toString(36);
    const copies: Node<CustomNodeData>[] = candidates.map((node, index) => ({
      ...node,
      id: `${node.type}_${timestamp}_dup${index}_${state.nodes.length + index + 1}`,
      position: { x: node.position.x + 48, y: node.position.y + 48 },
      selected: false,
      data: { ...node.data, config: node.data.config ? { ...node.data.config } : node.data.config },
    }));
    set((current) => ({
      history: pushHistory(current.history, current.nodes, current.edges),
      nodes: [...current.nodes, ...copies],
      selectedNodeId: copies[0]?.id ?? current.selectedNodeId,
      selectedEdgeId: "",
      validation: null,
    }));
    return copies.length;
  },

  deleteSelection: () => {
    const state = get();
    const removedNodeIds = new Set(
      state.nodes
        .filter((node) => (node.selected || node.id === state.selectedNodeId) && !isProtectedNode(node))
        .map((node) => node.id)
    );
    const removedEdgeIds = new Set(state.edges.filter((edge) => edge.selected).map((edge) => edge.id));
    if (state.selectedEdgeId) removedEdgeIds.add(state.selectedEdgeId);
    if (removedNodeIds.size === 0 && removedEdgeIds.size === 0) return;
    set((current) => ({
      history: pushHistory(current.history, current.nodes, current.edges),
      nodes: current.nodes.filter((node) => !removedNodeIds.has(node.id)),
      edges: current.edges.filter(
        (edge) =>
          !removedEdgeIds.has(edge.id) && !removedNodeIds.has(edge.source) && !removedNodeIds.has(edge.target)
      ),
      selectedNodeId: removedNodeIds.has(current.selectedNodeId) ? "" : current.selectedNodeId,
      selectedEdgeId: "",
      validation: null,
    }));
  },

  undo: () => {
    const { history } = get();
    const previous = history.past[history.past.length - 1];
    if (!previous) return;
    set((state) => ({
      history: {
        past: history.past.slice(0, -1),
        future: [...history.future, takeSnapshot(state.nodes, state.edges)],
      },
      nodes: previous.nodes,
      edges: previous.edges,
      selectedNodeId: previous.nodes.some((node) => node.id === state.selectedNodeId)
        ? state.selectedNodeId
        : "",
      selectedEdgeId: previous.edges.some((edge) => edge.id === state.selectedEdgeId)
        ? state.selectedEdgeId
        : "",
      validation: null,
    }));
  },

  redo: () => {
    const { history } = get();
    const next = history.future[history.future.length - 1];
    if (!next) return;
    set((state) => ({
      history: {
        past: [...history.past, takeSnapshot(state.nodes, state.edges)],
        future: history.future.slice(0, -1),
      },
      nodes: next.nodes,
      edges: next.edges,
      selectedNodeId: next.nodes.some((node) => node.id === state.selectedNodeId)
        ? state.selectedNodeId
        : "",
      selectedEdgeId: next.edges.some((edge) => edge.id === state.selectedEdgeId)
        ? state.selectedEdgeId
        : "",
      validation: null,
    }));
  },

  applyAutoLayout: () =>
    set((state) => {
      const positions = computeAutoLayoutPositions(state.nodes, state.edges);
      return {
        history: pushHistory(state.history, state.nodes, state.edges),
        nodes: state.nodes.map((node) =>
          positions.has(node.id) ? { ...node, position: positions.get(node.id) as { x: number; y: number } } : node
        ),
        validation: null,
      };
    }),

  setPendingAddPosition: (position) => set({ pendingAddPosition: position }),

  insertNodeIntoEdge: (edgeId, item, position) => {
    const state = get();
    const edge = state.edges.find((entry) => entry.id === edgeId);
    if (!edge) return false;
    const timestamp = Date.now().toString(36);
    const id = `${item.type}_${timestamp}_${state.nodes.length + 1}`;
    const branch =
      edge.sourceHandle === "true" || edge.sourceHandle === "false" ? edge.sourceHandle : undefined;
    const branchLabelStyle = branch ? { fill: "#475467", fontSize: 11, fontWeight: 600 } : undefined;
    set((current) => ({
      history: pushHistory(current.history, current.nodes, current.edges),
      nodes: [...current.nodes, makeNode(item.type, id, position)],
      edges: [
        ...current.edges.filter((entry) => entry.id !== edgeId),
        {
          id: `${edge.source}-${id}-${timestamp}`,
          source: edge.source,
          target: id,
          sourceHandle: branch,
          label: branch,
          labelStyle: branchLabelStyle,
          animated: true,
        },
        {
          id: `${id}-${edge.target}-${timestamp}`,
          source: id,
          target: edge.target,
          animated: true,
        },
      ],
      selectedNodeId: id,
      selectedEdgeId: "",
      validation: null,
    }));
    return true;
  },

  renameNode: (nodeId, displayName) =>
    set((state) => ({
      history: pushHistory(state.history, state.nodes, state.edges),
      nodes: state.nodes.map((node) =>
        node.id === nodeId
          ? {
              ...node,
              data: {
                ...node.data,
                config: { ...(node.data.config ?? {}), display_name: displayName },
              },
            }
          : node
      ),
      validation: null,
    })),

  copySelection: () => {
    const state = get();
    const selected = state.nodes.filter(
      (node) => (node.selected || node.id === state.selectedNodeId) && !isProtectedNode(node)
    );
    if (selected.length === 0) return 0;
    const minX = Math.min(...selected.map((node) => node.position.x));
    const minY = Math.min(...selected.map((node) => node.position.y));
    const payload = {
      kind: "agentflow-workflow-nodes",
      nodes: selected.map((node) => ({
        type: String(node.type ?? ""),
        offset: { x: node.position.x - minX, y: node.position.y - minY },
        config: node.data.config ?? {},
      })),
    };
    try {
      window.localStorage.setItem("agentflow-workflow-clipboard", JSON.stringify(payload));
    } catch {
      return 0;
    }
    return selected.length;
  },

  pasteClipboard: (position) => {
    if (typeof window === "undefined") return 0;
    let payload: {
      kind: string;
      nodes: Array<{ type: string; offset: { x: number; y: number }; config: Record<string, unknown> }>;
    } | null = null;
    try {
      payload = JSON.parse(window.localStorage.getItem("agentflow-workflow-clipboard") ?? "null");
    } catch {
      return 0;
    }
    if (!payload || payload.kind !== "agentflow-workflow-nodes" || payload.nodes.length === 0) return 0;
    const state = get();
    const anchor =
      position ??
      state.pendingAddPosition ?? {
        x: 200 + state.nodes.length * 16,
        y: 160 + state.nodes.length * 12,
      };
    const timestamp = Date.now().toString(36);
    const copies = payload.nodes.map((item, index) =>
      makeNode(
        item.type,
        `${item.type}_${timestamp}_paste${index}_${state.nodes.length + index + 1}`,
        { x: anchor.x + item.offset.x, y: anchor.y + item.offset.y },
        { ...item.config }
      )
    );
    set((current) => ({
      history: pushHistory(current.history, current.nodes, current.edges),
      nodes: [...current.nodes, ...copies],
      selectedNodeId: copies[0]?.id ?? current.selectedNodeId,
      selectedEdgeId: "",
      validation: null,
    }));
    return copies.length;
  },

  selectAllNodes: () =>
    set((state) => ({
      nodes: state.nodes.map((node) => ({ ...node, selected: true })),
    })),

  removeSelectedNode: () => {
    const state = get();
    const selectedNodeId = state.selectedNodeId;
    const selected = state.nodes.find((node) => node.id === selectedNodeId);
    if (!selectedNodeId || isProtectedNode(selected, selectedNodeId)) return;
    set((current) => ({
      history: pushHistory(current.history, current.nodes, current.edges),
      nodes: current.nodes.filter((node) => node.id !== selectedNodeId),
      edges: current.edges.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId),
      selectedNodeId: "",
      selectedEdgeId: "",
      validation: null,
    }));
  },

  removeSelectedEdge: () => {
    const selectedEdgeId = get().selectedEdgeId;
    if (!selectedEdgeId) return;
    set((state) => ({
      history: pushHistory(state.history, state.nodes, state.edges),
      edges: state.edges.filter((edge) => edge.id !== selectedEdgeId),
      selectedEdgeId: "",
      validation: null,
    }));
  },

  setSelectedNodeId: (id) => set({ selectedNodeId: id }),
  setSelectedEdgeId: (id) => set({ selectedEdgeId: id }),

  updateSelectedNodeConfig: (patch) => {
    const selectedNodeId = get().selectedNodeId;
    set((state) => ({
      nodes: state.nodes.map((node) =>
        node.id === selectedNodeId
          ? {
              ...node,
              data: {
                ...node.data,
                config: { ...(node.data.config ?? {}), ...patch },
              },
            }
          : node
      ),
      validation: null,
    }));
  },

  setWorkflowForm: (form) => set({ workflowForm: form }),
  setExecutionLimits: (executionLimits) => set({ executionLimits, validation: null }),

  applyWorkflowTemplate: (template) => {
    const definition = cloneWorkflowDefinition(template.definition);
    const nodes = hydrateNodes(definition);
    set((state) => ({
      history: pushHistory(state.history, state.nodes, state.edges),
      nodes,
      edges: hydrateEdges(definition),
      // A template is always a fresh draft. Retaining an existing ID would
      // let a later Save overwrite a customer's current workflow.
      selectedWorkflowId: "",
      selectedNodeId: nodes.find((node) => node.type !== "start")?.id ?? nodes[0]?.id ?? "",
      selectedEdgeId: "",
      selectedRunId: "",
      nodeRuns: [],
      workflowForm: {
        name: template.suggestedName,
        description: template.description,
        input: state.workflowForm.input,
      },
      executionLimits: editableExecutionLimits(definition),
      validation: null,
    }));
  },

  setSelectedWorkflowId: (id) => {
    const workflow = get().workflows.find((item) => item.workflow_id === id);
    if (!workflow) {
      set({ selectedWorkflowId: id });
      return;
    }
    const nodes = hydrateNodes(workflow.draft_definition);
    set({
      selectedWorkflowId: id,
      nodes,
      edges: hydrateEdges(workflow.draft_definition),
      selectedNodeId: nodes.find((node) => node.type !== "start")?.id ?? nodes[0]?.id ?? "",
      workflowForm: {
        name: workflow.name,
        description: workflow.description,
        input: get().workflowForm.input,
      },
      executionLimits: editableExecutionLimits(workflow.draft_definition),
      validation: null,
      history: { past: [], future: [] },
    });
  },

  setSelectedRunId: (id) => set({ selectedRunId: id }),

  resetCanvas: () =>
    set((state) => ({
      history: pushHistory(state.history, state.nodes, state.edges),
      nodes: INITIAL_NODES as Node<CustomNodeData>[],
      edges: INITIAL_EDGES as Edge[],
      selectedNodeId: "llm",
      selectedEdgeId: "",
      nodeRuns: [],
      executionLimits: { max_steps: "", max_llm_calls: "" },
      validation: null,
    })),

  getWorkflowDraft: () => {
    const { nodes, edges, executionLimits } = get();
    const runtime = useRuntimeStore.getState();
    const knowledge = useKnowledgeStore.getState();
    const firstTool = runtime.mcpTools[0] ?? null;

    const execution_limits = serializeExecutionLimits(executionLimits);
    return {
      version: "1.0",
      nodes: nodes.map((node) => {
        const nodeType = String(node.type ?? "");
        const config = { ...(node.data.config ?? {}) };
        if (nodeType === "llm") {
          config.provider = config.provider || runtime.selectedProviderKey;
          config.model = config.model || runtime.selectedModel;
        }
        if (nodeType === "rag") {
          config.kb_id = config.kb_id || knowledge.selectedKbId;
        }
        if (nodeType === "tool") {
          config.tool_id = config.tool_id || firstTool?.tool_id;
          config.tool_name = config.tool_name || firstTool?.name;
          config.risk_level = config.risk_level || firstTool?.risk_level || "low";
          config.arguments = parseMaybeJson(config.arguments);
        }
        if (nodeType === "http") {
          config.headers = parseMaybeJson(config.headers);
        }
        if (nodeType === "condition") {
          const operator = config.operator === "exists" ? "exists" : "equals";
          config.operator = operator;
          if (operator === "exists") {
            delete config.value;
          } else {
            config.value = coerceConditionValue(config.value, config.value_type);
          }
          delete config.value_type;
          delete config.expression;
          delete config.true_label;
          delete config.false_label;
        }
        return {
          id: node.id,
          type: nodeType,
          config: cleanConfig(config),
          position: { x: Math.round(node.position.x), y: Math.round(node.position.y) },
        };
      }),
      edges: edges.map((edge) => {
        const branch = edge.sourceHandle === "true" || edge.sourceHandle === "false"
          ? edge.sourceHandle
          : undefined;
        return { source: edge.source, target: edge.target, ...(branch ? { branch } : {}) };
      }),
      ...(execution_limits ? { execution_limits } : {}),
    };
  },

  createWorkflow: async (actorUserId, agentId) => {
    const { workflowForm, getWorkflowDraft } = get();
    if (!workflowForm.name.trim()) throw new Error("Please enter a workflow name");
    const workflow = await apiRequest<WorkflowItem>("/workflows", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        agent_id: agentId,
        name: workflowForm.name,
        description: workflowForm.description,
        draft_definition: getWorkflowDraft(),
      },
    });
    set((state) => ({
      workflows: [workflow, ...state.workflows],
      selectedWorkflowId: workflow.workflow_id,
    }));
  },

  saveWorkflowDraft: async (actorUserId) => {
    const { selectedWorkflowId, getWorkflowDraft } = get();
    if (!selectedWorkflowId) throw new Error("Please select a workflow first");
    const workflow = await apiRequest<WorkflowItem>(`/workflows/${selectedWorkflowId}/draft`, {
      method: "PUT",
      body: { actor_user_id: actorUserId, draft_definition: getWorkflowDraft() },
    });
    set((state) => ({
      workflows: state.workflows.map((item) =>
        item.workflow_id === workflow.workflow_id ? workflow : item
      ),
    }));
  },

  validateWorkflow: async (actorUserId) => {
    const { selectedWorkflowId, getWorkflowDraft } = get();
    if (!selectedWorkflowId) throw new Error("Please select a workflow first");
    const validation = await apiRequest<WorkflowValidationResult>(
      `/workflows/${selectedWorkflowId}/validate`,
      {
        method: "POST",
        body: {
          actor_user_id: actorUserId,
          draft_definition: getWorkflowDraft(),
        },
      }
    );
    set({ validation });
    return validation;
  },

  publishWorkflow: async (actorUserId) => {
    const { selectedWorkflowId } = get();
    if (!selectedWorkflowId) throw new Error("Please select a workflow first");
    await get().saveWorkflowDraft(actorUserId);
    const validation = await get().validateWorkflow(actorUserId);
    if (!validation.valid) {
      throw new Error(`运行前检查未通过：${validation.errors.join("；")}`);
    }
    const version = await apiRequest<WorkflowVersion>(`/workflows/${selectedWorkflowId}/publish`, {
      method: "POST",
      body: { actor_user_id: actorUserId },
    });
    set((state) => ({
      versions: [version, ...state.versions],
      workflows: state.workflows.map((item) =>
        item.workflow_id === selectedWorkflowId
          ? { ...item, published_version_id: version.version_id }
          : item
      ),
    }));
  },

  refreshVersions: async (workflowIds, actorUserId) => {
    const uniqueWorkflowIds = [...new Set(workflowIds.filter(Boolean))];
    if (uniqueWorkflowIds.length === 0) {
      set({ versions: [] });
      return;
    }
    const versionGroups = await Promise.all(
      uniqueWorkflowIds.map((workflowId) =>
        apiRequest<WorkflowVersion[]>(
          `/workflows/${workflowId}/versions?actor_user_id=${encodeURIComponent(actorUserId)}`
        )
      )
    );
    set({
      versions: versionGroups
        .flat()
        .sort((left, right) => right.created_at.localeCompare(left.created_at)),
    });
  },

  restoreVersionToDraft: async (actorUserId, versionId) => {
    const version = get().versions.find((item) => item.version_id === versionId);
    if (!version) throw new Error("The selected published version is no longer available");
    const workflow = await apiRequest<WorkflowItem>(
      `/workflows/${version.workflow_id}/versions/${versionId}/restore-draft`,
      {
        method: "POST",
        body: { actor_user_id: actorUserId },
      }
    );
    const nodes = hydrateNodes(workflow.draft_definition);
    set((state) => ({
      workflows: state.workflows.map((item) =>
        item.workflow_id === workflow.workflow_id ? workflow : item
      ),
      selectedWorkflowId: workflow.workflow_id,
      nodes,
      edges: hydrateEdges(workflow.draft_definition),
      selectedNodeId: nodes.find((node) => node.type !== "start")?.id ?? nodes[0]?.id ?? "",
      selectedEdgeId: "",
      executionLimits: editableExecutionLimits(workflow.draft_definition),
      validation: null,
      history: { past: [], future: [] },
    }));
  },

  runWorkflow: async (actorUserId, input) => {
    const { selectedWorkflowId, workflows } = get();
    if (!selectedWorkflowId) throw new Error("Please select a workflow first");
    const workflow = workflows.find((item) => item.workflow_id === selectedWorkflowId);
    if (!workflow?.published_version_id) throw new Error("Please publish the workflow first");
    const run = await apiRequest<WorkflowRun>("/workflow-runs", {
      method: "POST",
      body: {
        version_id: workflow.published_version_id,
        input_data: { text: input },
        async_mode: false,
      },
    });
    const nodeRuns = await apiRequest<NodeRun[]>(
      `/workflow-runs/${run.run_id}/nodes?actor_user_id=${actorUserId}`
    );
    set((state) => ({
      runs: [run, ...state.runs],
      selectedRunId: run.run_id,
      nodeRuns,
    }));
  },

  loadNodeRuns: async (runId, actorUserId) => {
    const nodeRuns = await apiRequest<NodeRun[]>(
      `/workflow-runs/${runId}/nodes?actor_user_id=${actorUserId}`
    );
    set({ nodeRuns, selectedRunId: runId });
  },

  clearRunSelection: () => set({ selectedRunId: "", nodeRuns: [] }),

  resetWorkspaceData: () =>
    set({
      nodes: INITIAL_NODES as Node<CustomNodeData>[],
      edges: INITIAL_EDGES as Edge[],
      workflows: [],
      selectedWorkflowId: "",
      selectedNodeId: "llm",
      selectedEdgeId: "",
      versions: [],
      runs: [],
      selectedRunId: "",
      nodeRuns: [],
      workflowForm: { name: "", description: "", input: "" },
      executionLimits: { max_steps: "", max_llm_calls: "" },
      validation: null,
      history: { past: [], future: [] },
      pendingAddPosition: null,
    }),

  refreshWorkflows: async (orgId, actorUserId, agentId) => {
    const params = new URLSearchParams({ org_id: orgId, actor_user_id: actorUserId });
    if (agentId) params.set("agent_id", agentId);
    const workflows = await apiRequest<WorkflowItem[]>(`/workflows?${params.toString()}`);
    set((state) => {
      const selectedWorkflowId = workflows.some((item) => item.workflow_id === state.selectedWorkflowId)
        ? state.selectedWorkflowId
        : workflows[0]?.workflow_id || "";
      const selectedWorkflow = workflows.find((item) => item.workflow_id === selectedWorkflowId);
      const nodes = selectedWorkflow ? hydrateNodes(selectedWorkflow.draft_definition) : state.nodes;
      return {
        workflows,
        selectedWorkflowId,
        nodes,
        edges: selectedWorkflow ? hydrateEdges(selectedWorkflow.draft_definition) : state.edges,
        selectedNodeId: nodes.find((node) => node.type !== "start")?.id ?? nodes[0]?.id ?? "",
        selectedEdgeId: "",
        executionLimits: selectedWorkflow
          ? editableExecutionLimits(selectedWorkflow.draft_definition)
          : state.executionLimits,
        validation: null,
        history: selectedWorkflow && selectedWorkflowId === state.selectedWorkflowId
          ? state.history
          : { past: [], future: [] },
      };
    });
  },

  refreshRuns: async (orgId, actorUserId) => {
    const runs = await apiRequest<WorkflowRun[]>(
      `/workflow-runs?org_id=${orgId}&actor_user_id=${actorUserId}`
    );
    set((state) => ({
      runs,
      selectedRunId: state.selectedRunId || runs[0]?.run_id || "",
    }));
  },
}));
