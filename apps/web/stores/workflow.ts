/** Workflow 状态管理。

管理工作流列表、画布节点/边、工作流运行等状态。
 */

import { create } from "zustand";
import {
  type Node,
  type Edge,
  type Connection,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  type NodeChange,
  type EdgeChange,
} from "@xyflow/react";
import type {
  WorkflowItem,
  WorkflowRun,
  WorkflowVersion,
  NodeRun,
  WorkflowDefinition,
  LLMNodeForm,
  RAGNodeForm,
  ToolNodeForm,
} from "@/types/workflow";
import { apiRequest } from "@/lib/api";
import { wsManager, type WorkflowRunEvent } from "@/lib/websocket";
import { INITIAL_NODES, INITIAL_EDGES } from "@/lib/constants";

interface WorkflowStore {
  /** 画布节点 */
  nodes: Node[];
  /** 画布边 */
  edges: Edge[];
  /** 工作流列表 */
  workflows: WorkflowItem[];
  /** 当前选中的工作流 ID */
  selectedWorkflowId: string;
  /** 工作流版本列表 */
  versions: WorkflowVersion[];
  /** 工作流运行列表 */
  runs: WorkflowRun[];
  /** 当前选中的运行 ID */
  selectedRunId: string;
  /** 节点运行日志 */
  nodeRuns: NodeRun[];

  /** LLM 节点表单 */
  llmNodeForm: LLMNodeForm;
  /** RAG 节点表单 */
  ragNodeForm: RAGNodeForm;
  /** Tool 节点表单 */
  toolNodeForm: ToolNodeForm;

  /** 工作流表单 */
  workflowForm: { name: string; description: string; input: string };

  // Actions - 画布
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  addNode: (label: string, type: string) => void;

  // Actions - 表单
  setLLMNodeForm: (form: LLMNodeForm) => void;
  setRAGNodeForm: (form: RAGNodeForm) => void;
  setToolNodeForm: (form: ToolNodeForm) => void;
  setWorkflowForm: (form: { name: string; description: string; input: string }) => void;
  setSelectedWorkflowId: (id: string) => void;
  setSelectedRunId: (id: string) => void;

  // Actions - API
  createWorkflow: (actorUserId: string, agentId: string) => Promise<void>;
  saveWorkflowDraft: (actorUserId: string) => Promise<void>;
  publishWorkflow: (actorUserId: string) => Promise<void>;
  runWorkflow: (actorUserId: string, input: string) => Promise<void>;
  loadNodeRuns: (runId: string, actorUserId: string) => Promise<void>;
  refreshWorkflows: (orgId: string, actorUserId: string) => Promise<void>;
  refreshRuns: (orgId: string, actorUserId: string) => Promise<void>;

  /** 获取当前工作流 DSL */
  getWorkflowDraft: () => WorkflowDefinition;
}

/** 安全解析 JSON 对象 */
function parseJsonObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export const useWorkflowStore = create<WorkflowStore>((set, get) => ({
  nodes: INITIAL_NODES as Node[],
  edges: INITIAL_EDGES as Edge[],
  workflows: [],
  selectedWorkflowId: "",
  versions: [],
  runs: [],
  selectedRunId: "",
  nodeRuns: [],

  llmNodeForm: {
    systemPrompt: "你是一个可靠的业务 Agent，先给结论，再给依据。",
    prompt: "请总结输入，并给出下一步建议。",
    temperature: "0",
  },
  ragNodeForm: {
    queryTemplate: "{{input.text}}",
    limit: "5",
  },
  toolNodeForm: {
    toolId: "",
    arguments: '{\n  "query": "{{input.text}}"\n}',
  },
  workflowForm: {
    name: "客户问题处理流",
    description: "Start -> LLM -> End 的最小可运行工作流。",
    input: "请总结这个客户问题，并给出下一步处理建议。",
  },

  onNodesChange: (changes) => {
    set((state) => ({ nodes: applyNodeChanges(changes, state.nodes) }));
  },
  onEdgesChange: (changes) => {
    set((state) => ({ edges: applyEdgeChanges(changes, state.edges) }));
  },
  onConnect: (connection) => {
    set((state) => ({ edges: addEdge(connection, state.edges) }));
  },
  addNode: (label, type) => {
    const { nodes } = get();
    const nodeIndex = nodes.length + 1;
    const newNode: Node = {
      id: `${type}_${nodeIndex}`,
      type,
      position: { x: 320 + nodeIndex * 28, y: 300 },
      data: { label },
    };
    set({ nodes: [...nodes, newNode] });
  },

  setLLMNodeForm: (form) => set({ llmNodeForm: form }),
  setRAGNodeForm: (form) => set({ ragNodeForm: form }),
  setToolNodeForm: (form) => set({ toolNodeForm: form }),
  setWorkflowForm: (form) => set({ workflowForm: form }),
  setSelectedWorkflowId: (id) => set({ selectedWorkflowId: id }),
  setSelectedRunId: (id) => set({ selectedRunId: id }),

  getWorkflowDraft: () => {
    const { nodes, edges, llmNodeForm, ragNodeForm, toolNodeForm } = get();
    return {
      version: "1.0",
      nodes: nodes.map((node) => {
        const label = String(node.data.label);
        return {
          id: node.id,
          type: label.toLowerCase(),
          config: {
            label,
            system_prompt: label === "LLM" ? llmNodeForm.systemPrompt : undefined,
            prompt: label === "LLM" ? llmNodeForm.prompt : undefined,
            temperature: label === "LLM" ? Number(llmNodeForm.temperature || 0) : undefined,
            query_template: label === "RAG" ? ragNodeForm.queryTemplate : undefined,
            limit: label === "RAG" ? Number(ragNodeForm.limit || 5) : undefined,
            arguments: label === "Tool" ? parseJsonObject(toolNodeForm.arguments) : undefined,
          },
        };
      }),
      edges: edges.map((edge) => ({ source: edge.source, target: edge.target })),
    };
  },

  createWorkflow: async (actorUserId, agentId) => {
    const { getWorkflowDraft, workflowForm } = get();
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
      workflows: [...state.workflows, workflow],
      selectedWorkflowId: workflow.workflow_id,
    }));
  },

  saveWorkflowDraft: async (actorUserId) => {
    const { selectedWorkflowId, getWorkflowDraft } = get();
    if (!selectedWorkflowId) throw new Error("请先创建或选择 Workflow。");
    await apiRequest<WorkflowItem>(`/workflows/${selectedWorkflowId}/draft`, {
      method: "PUT",
      body: { actor_user_id: actorUserId, draft_definition: getWorkflowDraft() },
    });
  },

  publishWorkflow: async (actorUserId) => {
    const { selectedWorkflowId } = get();
    if (!selectedWorkflowId) throw new Error("请先创建或选择 Workflow。");
    const version = await apiRequest<WorkflowVersion>(`/workflows/${selectedWorkflowId}/publish`, {
      method: "POST",
      body: { actor_user_id: actorUserId },
    });
    set((state) => ({ versions: [version, ...state.versions] }));
  },

  runWorkflow: async (actorUserId, input) => {
    const { selectedWorkflowId, workflows } = get();
    if (!selectedWorkflowId) throw new Error("请先创建或选择 Workflow。");

    const workflow = workflows.find((w) => w.workflow_id === selectedWorkflowId);
    const versionId = workflow?.published_version_id;
    if (!versionId) throw new Error("请先发布 Workflow，再运行。");

    const run = await apiRequest<WorkflowRun>("/workflow-runs", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        version_id: versionId,
        input_data: { text: input },
        async_mode: false,
      },
    });

    set({ selectedRunId: run.run_id });

    // 加载节点运行日志
    const nodeRuns = await apiRequest<NodeRun[]>(
      `/workflow-runs/${run.run_id}/nodes?actor_user_id=${actorUserId}`
    );
    set({ nodeRuns });
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
    set({ workflows });
  },

  refreshRuns: async (orgId, actorUserId) => {
    const runs = await apiRequest<WorkflowRun[]>(
      `/workflow-runs?org_id=${orgId}&actor_user_id=${actorUserId}`
    );
    set({ runs });
  },

  /** 订阅 Workflow 运行实时更新 */
  subscribeRunUpdates: () => {
    return wsManager.on("workflow_run", (event, data) => {
      const runEvent = data as WorkflowRunEvent;
      set((state) => ({
        runs: state.runs.map((r) =>
          r.run_id === runEvent.run_id ? { ...r, status: runEvent.status } : r
        ),
      }));
    });
  },
}));
