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
  removeSelectedNode: () => void;
  removeSelectedEdge: () => void;
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
  return definition.nodes.map((node, index) =>
    makeNode(node.type, node.id, { x: 80 + index * 280, y: 260 }, node.config)
  );
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

  onNodesChange: (changes) =>
    set((state) => ({
      nodes: applyNodeChanges(changes, state.nodes) as Node<CustomNodeData>[],
      validation: null,
    })),
  onEdgesChange: (changes) =>
    set((state) => ({
      edges: applyEdgeChanges(changes, state.edges),
      validation: null,
      selectedEdgeId: changes.some((change) => change.type === "remove" && change.id === state.selectedEdgeId)
        ? ""
        : state.selectedEdgeId,
    })),
  validateConnection: (sourceId, targetId, branch) =>
    checkConnection(get().nodes, get().edges, sourceId, targetId, branch),

  connectNodes: (sourceId, targetId, branch) => {
    const result = get().validateConnection(sourceId, targetId, branch);
    if (!result.valid) return result;

    set((state) => ({
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
      const sourceNode = state.nodes.find((node) => node.id === sourceId);
      const replacedEdge = state.edges.find((edge) => edge.id === replacedEdgeId);
      const inheritedBranch = sourceNode?.type === "condition" &&
        (replacedEdge?.sourceHandle === "true" || replacedEdge?.sourceHandle === "false")
        ? replacedEdge.sourceHandle
        : undefined;
      const insertedEdges = sourceId
        ? [
            {
              id: `${sourceId}-${id}-${timestamp}`,
              source: sourceId,
              target: id,
              sourceHandle: inheritedBranch,
              label: inheritedBranch,
              animated: true,
            },
            ...(targetId && item.type === "condition"
              ? (["true", "false"] as const).map((branch) => ({
                  id: `${id}-${branch}-${targetId}-${timestamp}`,
                  source: id,
                  target: targetId,
                  sourceHandle: branch,
                  label: branch,
                  animated: true,
                }))
              : targetId
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
        validation: null,
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
      selectedEdgeId: "",
      validation: null,
    }));
  },

  removeSelectedEdge: () => {
    const selectedEdgeId = get().selectedEdgeId;
    if (!selectedEdgeId) return;
    set((state) => ({
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
    });
  },

  setSelectedRunId: (id) => set({ selectedRunId: id }),

  resetCanvas: () =>
    set({
      nodes: INITIAL_NODES as Node<CustomNodeData>[],
      edges: INITIAL_EDGES as Edge[],
      selectedNodeId: "llm",
      nodeRuns: [],
      executionLimits: { max_steps: "", max_llm_calls: "" },
      validation: null,
    }),

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
        return { id: node.id, type: nodeType, config: cleanConfig(config) };
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
