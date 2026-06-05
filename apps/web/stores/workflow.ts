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
import { apiRequest } from "@/lib/api";
import { INITIAL_EDGES, INITIAL_NODES, type WorkflowPaletteItem } from "@/lib/constants";
import { useKnowledgeStore } from "@/stores/knowledge";
import { useRuntimeStore } from "@/stores/runtime";
import type {
  CustomNodeData,
  NodeRun,
  WorkflowDefinition,
  WorkflowItem,
  WorkflowRun,
  WorkflowVersion,
} from "@/types/workflow";

interface WorkflowStore {
  nodes: Node<CustomNodeData>[];
  edges: Edge[];
  workflows: WorkflowItem[];
  selectedWorkflowId: string;
  selectedNodeId: string;
  versions: WorkflowVersion[];
  runs: WorkflowRun[];
  selectedRunId: string;
  nodeRuns: NodeRun[];
  workflowForm: { name: string; description: string; input: string };

  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  addNode: (item: WorkflowPaletteItem) => void;
  removeSelectedNode: () => void;
  setSelectedNodeId: (id: string) => void;
  updateSelectedNodeConfig: (patch: Record<string, unknown>) => void;
  setWorkflowForm: (form: { name: string; description: string; input: string }) => void;
  setSelectedWorkflowId: (id: string) => void;
  setSelectedRunId: (id: string) => void;
  resetCanvas: () => void;
  getWorkflowDraft: () => WorkflowDefinition;
  createWorkflow: (actorUserId: string, agentId: string) => Promise<void>;
  saveWorkflowDraft: (actorUserId: string) => Promise<void>;
  publishWorkflow: (actorUserId: string) => Promise<void>;
  runWorkflow: (actorUserId: string, input: string) => Promise<void>;
  loadNodeRuns: (runId: string, actorUserId: string) => Promise<void>;
  refreshWorkflows: (orgId: string, actorUserId: string) => Promise<void>;
  refreshRuns: (orgId: string, actorUserId: string) => Promise<void>;
}

const NODE_META: Record<string, { label: string; description: string; capability: "executable" | "schema" }> = {
  start: { label: "Start", description: "Workflow input", capability: "executable" },
  end: { label: "End", description: "Workflow result", capability: "executable" },
  llm: { label: "LLM", description: "Model call", capability: "executable" },
  rag: { label: "Knowledge Retrieval", description: "Vector knowledge search", capability: "executable" },
  tool: { label: "Tool", description: "Authorized MCP tool plan", capability: "executable" },
  condition: { label: "Condition", description: "Branch by expression", capability: "schema" },
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
      return { expression: "{{input.status}} == 'ok'", true_label: "true", false_label: "false" };
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
  return {
    id,
    type,
    position,
    data: {
      label: meta.label,
      description: meta.description,
      capability: meta.capability,
      config: { ...defaultConfig(type), ...(config ?? {}) },
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
  return definition.nodes.map((node, index) =>
    makeNode(node.type, node.id, { x: 80 + index * 280, y: 260 }, node.config)
  );
}

function hydrateEdges(definition: WorkflowDefinition): Edge[] {
  return definition.edges.map((edge, index) => ({
    id: `${edge.source}-${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
  }));
}

export const useWorkflowStore = create<WorkflowStore>((set, get) => ({
  nodes: INITIAL_NODES as Node<CustomNodeData>[],
  edges: INITIAL_EDGES as Edge[],
  workflows: [],
  selectedWorkflowId: "",
  selectedNodeId: "llm",
  versions: [],
  runs: [],
  selectedRunId: "",
  nodeRuns: [],
  workflowForm: { name: "", description: "", input: "" },

  onNodesChange: (changes) =>
    set((state) => ({ nodes: applyNodeChanges(changes, state.nodes) as Node<CustomNodeData>[] })),
  onEdgesChange: (changes) => set((state) => ({ edges: applyEdgeChanges(changes, state.edges) })),
  onConnect: (connection) => set((state) => ({ edges: addEdge(connection, state.edges) })),

  addNode: (item) => {
    const nodeIndex = get().nodes.length + 1;
    const timestamp = Date.now().toString(36);
    const id = `${item.type}_${timestamp}_${nodeIndex}`;
    set((state) => {
      let anchor = state.nodes.find((node) => node.id === state.selectedNodeId)
        ?? state.nodes.find((node) => node.id === "llm")
        ?? state.nodes[0];
      let sourceId = anchor?.id ?? "";
      let targetId = "";
      let replacedEdgeId = "";

      if (anchor?.type === "end") {
        const incomingEdge = state.edges.find((edge) => edge.target === anchor?.id);
        if (incomingEdge) {
          sourceId = incomingEdge.source;
          targetId = incomingEdge.target;
          replacedEdgeId = incomingEdge.id;
          anchor = state.nodes.find((node) => node.id === sourceId) ?? anchor;
        }
      } else if (sourceId) {
        const outgoingEdge = state.edges.find((edge) => edge.source === sourceId);
        if (outgoingEdge) {
          targetId = outgoingEdge.target;
          replacedEdgeId = outgoingEdge.id;
        }
      }

      const basePosition = anchor?.position ?? { x: 260, y: 260 };
      const position = { x: basePosition.x + 300, y: basePosition.y };
      const shiftedNodes = state.nodes.map((node) => {
        if (node.position.x >= position.x && node.id !== sourceId) {
          return { ...node, position: { ...node.position, x: node.position.x + 280 } };
        }
        return node;
      });
      const remainingEdges = replacedEdgeId
        ? state.edges.filter((edge) => edge.id !== replacedEdgeId)
        : state.edges;
      const insertedEdges = sourceId
        ? [
            {
              id: `${sourceId}-${id}-${timestamp}`,
              source: sourceId,
              target: id,
              animated: true,
            },
            ...(targetId
              ? [{
                  id: `${id}-${targetId}-${timestamp}`,
                  source: id,
                  target: targetId,
                  animated: true,
                }]
              : []),
          ]
        : [];

      return {
        nodes: [...shiftedNodes, makeNode(item.type, id, position)],
        edges: [...remainingEdges, ...insertedEdges],
        selectedNodeId: id,
      };
    });
  },

  removeSelectedNode: () => {
    const selectedNodeId = get().selectedNodeId;
    if (!selectedNodeId || selectedNodeId === "start" || selectedNodeId === "end") return;
    set((state) => ({
      nodes: state.nodes.filter((node) => node.id !== selectedNodeId),
      edges: state.edges.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId),
      selectedNodeId: "llm",
    }));
  },

  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

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
    }));
  },

  setWorkflowForm: (form) => set({ workflowForm: form }),

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
    });
  },

  setSelectedRunId: (id) => set({ selectedRunId: id }),

  resetCanvas: () =>
    set({
      nodes: INITIAL_NODES as Node<CustomNodeData>[],
      edges: INITIAL_EDGES as Edge[],
      selectedNodeId: "llm",
      nodeRuns: [],
    }),

  getWorkflowDraft: () => {
    const { nodes, edges } = get();
    const runtime = useRuntimeStore.getState();
    const knowledge = useKnowledgeStore.getState();
    const firstTool = runtime.mcpTools[0] ?? null;

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
        return { id: node.id, type: nodeType, config: cleanConfig(config) };
      }),
      edges: edges.map((edge) => ({ source: edge.source, target: edge.target })),
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

  publishWorkflow: async (actorUserId) => {
    const { selectedWorkflowId } = get();
    if (!selectedWorkflowId) throw new Error("Please select a workflow first");
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

  runWorkflow: async (actorUserId, input) => {
    const { selectedWorkflowId, workflows } = get();
    if (!selectedWorkflowId) throw new Error("Please select a workflow first");
    const workflow = workflows.find((item) => item.workflow_id === selectedWorkflowId);
    if (!workflow?.published_version_id) throw new Error("Please publish the workflow first");
    const run = await apiRequest<WorkflowRun>("/workflow-runs", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
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

  refreshWorkflows: async (orgId, actorUserId) => {
    const workflows = await apiRequest<WorkflowItem[]>(
      `/workflows?org_id=${orgId}&actor_user_id=${actorUserId}`
    );
    set((state) => {
      const selectedWorkflowId = state.selectedWorkflowId || workflows[0]?.workflow_id || "";
      const selectedWorkflow = workflows.find((item) => item.workflow_id === selectedWorkflowId);
      const nodes = selectedWorkflow ? hydrateNodes(selectedWorkflow.draft_definition) : state.nodes;
      return {
        workflows,
        selectedWorkflowId,
        nodes,
        edges: selectedWorkflow ? hydrateEdges(selectedWorkflow.draft_definition) : state.edges,
        selectedNodeId: nodes.find((node) => node.type !== "start")?.id ?? nodes[0]?.id ?? "",
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
