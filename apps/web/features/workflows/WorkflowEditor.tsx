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
import {
  Activity,
  Bot,
  Brain,
  CheckCircle2,
  Database,
  FileText,
  GitBranch,
  Loader2,
  MessageSquare,
  Network,
  Play,
  Plus,
  Save,
  Server,
  ShieldCheck,
  Workflow
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type ApiStatus = "checking" | "online" | "offline";
type ToastKind = "info" | "success" | "error";

type WorkspaceState = {
  userId: string;
  orgId: string;
  teamId: string;
  email: string;
};

type Agent = {
  agent_id: string;
  org_id: string;
  team_id: string | null;
  name: string;
  description: string;
};

type WorkflowItem = {
  workflow_id: string;
  agent_id: string;
  name: string;
  description: string;
  draft_definition: Record<string, unknown>;
  published_version_id: string | null;
};

type WorkflowVersion = {
  version_id: string;
  version_number: number;
};

type WorkflowRun = {
  run_id: string;
  workflow_id: string;
  version_id: string;
  agent_id: string;
  status: string;
  output_data: Record<string, unknown>;
  error_message: string;
};

type NodeRun = {
  node_run_id: string;
  node_id: string;
  node_type: string;
  status: string;
  elapsed_ms: number;
};

type Skill = {
  skill_id: string;
  name: string;
  description: string;
  scope: string;
};

type MCPServer = {
  server_id: string;
  name: string;
  transport: string;
  url: string;
};

type MCPTool = {
  tool_id: string;
  name: string;
  description: string;
  risk_level: string;
};

type MemoryItem = {
  memory_id: string;
  memory_type: string;
  summary: string;
  confidence: number;
};

type SessionItem = {
  session_id: string;
  status: string;
  compact_summary: string;
};

type ContextBundle = {
  total_estimated_tokens: number;
  need_compaction: boolean;
  sections: Array<{ name: string; content: string; estimated_tokens: number }>;
};

type LLMCallLog = {
  call_id: string;
  provider: string;
  model: string;
  status: string;
  prefix_hash: string;
};

type ModelProvider = {
  provider_id: string;
  provider_key: string;
  display_name: string;
  base_url: string;
  api_key_masked: string;
  models: string[];
  default_model: string;
  is_enabled: boolean;
};

type ApiErrorPayload = {
  detail?: string | { msg?: string } | Array<{ msg?: string }>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const initialNodes: Node[] = [
  { id: "start", type: "default", position: { x: 70, y: 180 }, data: { label: "Start" } },
  { id: "llm", type: "default", position: { x: 360, y: 180 }, data: { label: "LLM" } },
  { id: "end", type: "default", position: { x: 650, y: 180 }, data: { label: "End" } }
];

const initialEdges: Edge[] = [
  { id: "start-llm", source: "start", target: "llm" },
  { id: "llm-end", source: "llm", target: "end" }
];

const navItems = [
  { key: "agents", label: "Agents", icon: Bot },
  { key: "workflow", label: "Workflow", icon: Workflow },
  { key: "runtime", label: "Runtime", icon: Brain },
  { key: "runs", label: "Runs", icon: Activity }
] as const;

type ActiveSection = (typeof navItems)[number]["key"];

const nodePalette = [
  { label: "LLM", description: "模型推理", icon: Bot },
  { label: "RAG", description: "知识检索", icon: Database },
  { label: "Tool", description: "工具调用", icon: ShieldCheck }
];

export default function WorkflowEditor() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [activeSection, setActiveSection] = useState<ActiveSection>("agents");
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ kind: ToastKind; text: string }>({
    kind: "info",
    text: "创建一个工作空间后即可开始搭建 Agent 应用。"
  });

  const [workspace, setWorkspace] = useState<WorkspaceState | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [nodeRuns, setNodeRuns] = useState<NodeRun[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [contextBundle, setContextBundle] = useState<ContextBundle | null>(null);
  const [gatewayLogs, setGatewayLogs] = useState<LLMCallLog[]>([]);
  const [modelProviders, setModelProviders] = useState<ModelProvider[]>([]);
  const [selectedProviderKey, setSelectedProviderKey] = useState("mock");
  const [selectedModel, setSelectedModel] = useState("mock-model");

  const [setupForm, setSetupForm] = useState({
    email: "owner@example.com",
    displayName: "Owner",
    orgName: "AgentFlow 工作空间",
    teamName: "默认团队"
  });
  const [agentForm, setAgentForm] = useState({
    name: "客服助手 Agent",
    description: "负责基于知识、工具和工作流回答用户问题。"
  });
  const [workspaceText, setWorkspaceText] = useState("# AGENTS\n\n你是一个可靠的业务 Agent，回答时先给结论，再给依据。\n");
  const [workflowForm, setWorkflowForm] = useState({
    name: "客户问题处理流",
    description: "Start -> LLM -> End 的最小可运行工作流。",
    input: "请总结这个客户问题，并给出下一步处理建议。"
  });
  const [skillForm, setSkillForm] = useState({
    name: "workflow-reviewer",
    description: "检查工作流结构并给出改进建议"
  });
  const [memoryForm, setMemoryForm] = useState("用户偏好中文、先给结论、再给验证证据。");
  const [mcpForm, setMcpForm] = useState({
    serverName: "知识库 MCP",
    url: "http://localhost:18080/mcp",
    toolName: "search_docs"
  });
  const [sessionInput, setSessionInput] = useState("请结合工作区、Skill、MCP 和 Memory 输出一次响应。");

  const [providerForm, setProviderForm] = useState({
    providerKey: "deepseek",
    displayName: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    apiKey: "",
    models: "deepseek-chat, deepseek-reasoner",
    defaultModel: "deepseek-chat"
  });
  const [llmNodeForm, setLlmNodeForm] = useState({
    systemPrompt: "你是一个可靠的业务 Agent，先给结论，再给依据。",
    prompt: "请总结输入，并给出下一步建议。",
    temperature: "0"
  });

  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? null;
  const selectedWorkflow = workflows.find((workflow) => workflow.workflow_id === selectedWorkflowId) ?? null;
  const selectedRun = runs.find((run) => run.run_id === selectedRunId) ?? null;
  const modelOptions =
    selectedProviderKey === "mock"
      ? ["mock-model"]
      : modelProviders.find((provider) => provider.provider_key === selectedProviderKey)?.models ?? ["mock-model"];

  const workflowDraft = useMemo(() => {
    return {
      version: "1.0",
      nodes: nodes.map((node) => {
        const label = String(node.data.label);

        return {
          id: node.id,
          type: label.toLowerCase(),
          config: {
            label,
            provider: label === "LLM" ? selectedProviderKey : undefined,
            model: label === "LLM" ? selectedModel : undefined,
            system_prompt: label === "LLM" ? llmNodeForm.systemPrompt : undefined,
            prompt: label === "LLM" ? llmNodeForm.prompt : undefined,
            temperature: label === "LLM" ? Number(llmNodeForm.temperature || 0) : undefined,
            collection: label === "RAG" ? "default" : undefined,
            tool_name: label === "Tool" ? mcpForm.toolName : undefined
          }
        };
      }),
      edges: edges.map((edge) => ({ source: edge.source, target: edge.target }))
    };
  }, [nodes, edges, selectedProviderKey, selectedModel, llmNodeForm, mcpForm.toolName]);

  useEffect(() => {
    let mounted = true;

    async function checkHealth() {
      try {
        const response = await apiRequest<{ status: string }>("/health");
        if (mounted) setApiStatus(response.status === "ok" ? "online" : "offline");
      } catch {
        if (mounted) setApiStatus("offline");
      }
    }

    void checkHealth();
    return () => {
      mounted = false;
    };
  }, []);

  function showToast(kind: ToastKind, text: string) {
    setToast({ kind, text });
  }

  function requireWorkspace() {
    if (!workspace) throw new Error("请先创建工作空间。");
    return workspace;
  }

  function requireAgent() {
    if (!selectedAgentId) throw new Error("请先创建或选择 Agent。");
    return selectedAgentId;
  }

  function handleConnect(connection: Connection) {
    setEdges((currentEdges) => addEdge(connection, currentEdges));
  }

  function addNode(label: string) {
    const nodeIndex = nodes.length + 1;
    setNodes((currentNodes) => [
      ...currentNodes,
      {
        id: `${label.toLowerCase()}_${nodeIndex}`,
        type: "default",
        position: { x: 320 + nodeIndex * 28, y: 300 },
        data: { label }
      }
    ]);
  }

  async function refreshAgents(currentWorkspace = workspace) {
    if (!currentWorkspace) return;
    const nextAgents = await apiRequest<Agent[]>(
      `/agents?org_id=${currentWorkspace.orgId}&actor_user_id=${currentWorkspace.userId}`
    );
    setAgents(nextAgents);
    if (!selectedAgentId && nextAgents[0]) setSelectedAgentId(nextAgents[0].agent_id);
  }

  async function refreshStudioData(currentWorkspace = workspace, agentId = selectedAgentId) {
    if (!currentWorkspace) return;

    const [nextAgents, nextWorkflows, nextRuns, nextSkills, nextServers, nextLogs, nextProviders] = await Promise.all([
      apiRequest<Agent[]>(`/agents?org_id=${currentWorkspace.orgId}&actor_user_id=${currentWorkspace.userId}`),
      apiRequest<WorkflowItem[]>(`/workflows?org_id=${currentWorkspace.orgId}&actor_user_id=${currentWorkspace.userId}`),
      apiRequest<WorkflowRun[]>(`/workflow-runs?org_id=${currentWorkspace.orgId}&actor_user_id=${currentWorkspace.userId}`),
      apiRequest<Skill[]>(`/skills?org_id=${currentWorkspace.orgId}&actor_user_id=${currentWorkspace.userId}`),
      apiRequest<MCPServer[]>(`/mcp/servers?org_id=${currentWorkspace.orgId}&actor_user_id=${currentWorkspace.userId}`),
      apiRequest<LLMCallLog[]>("/gateway/llm/logs"),
      apiRequest<ModelProvider[]>(`/model-providers?org_id=${currentWorkspace.orgId}&actor_user_id=${currentWorkspace.userId}`)
    ]);

    setAgents(nextAgents);
    setWorkflows(nextWorkflows);
    setRuns(nextRuns);
    setSkills(nextSkills);
    setMcpServers(nextServers);
    setGatewayLogs(nextLogs);
    setModelProviders(nextProviders);

    const fallbackAgentId = agentId || nextAgents[0]?.agent_id || "";
    if (fallbackAgentId) {
      setSelectedAgentId(fallbackAgentId);
      const [nextSessions, nextMemories, nextTools] = await Promise.all([
        apiRequest<SessionItem[]>(`/sessions?agent_id=${fallbackAgentId}&actor_user_id=${currentWorkspace.userId}`),
        apiRequest<MemoryItem[]>(`/memory?agent_id=${fallbackAgentId}&actor_user_id=${currentWorkspace.userId}`),
        apiRequest<MCPTool[]>(`/mcp/agents/${fallbackAgentId}/tools?actor_user_id=${currentWorkspace.userId}`)
      ]);
      setSessions(nextSessions);
      setMemories(nextMemories);
      setMcpTools(nextTools);
    }

    if (!selectedWorkflowId && nextWorkflows[0]) setSelectedWorkflowId(nextWorkflows[0].workflow_id);
    if (!selectedRunId && nextRuns[0]) setSelectedRunId(nextRuns[0].run_id);
  }

  async function createWorkspace() {
    setBusy(true);
    try {
      const timestamp = Date.now();
      const email = setupForm.email.includes("@") ? setupForm.email : `owner-${timestamp}@example.com`;
      const user = await apiRequest<{ user_id: string }>("/identity/users/register", {
        method: "POST",
        body: {
          email: email.replace("@example.com", `-${timestamp}@example.com`),
          display_name: setupForm.displayName,
          password: "password123"
        }
      });
      const organization = await apiRequest<{ org_id: string }>("/identity/organizations", {
        method: "POST",
        body: { creator_user_id: user.user_id, name: setupForm.orgName }
      });
      const team = await apiRequest<{ team_id: string }>(`/identity/organizations/${organization.org_id}/teams`, {
        method: "POST",
        body: { actor_user_id: user.user_id, name: setupForm.teamName }
      });
      const nextWorkspace = {
        userId: user.user_id,
        orgId: organization.org_id,
        teamId: team.team_id,
        email
      };
      setWorkspace(nextWorkspace);
      showToast("success", "工作空间已创建，可以开始创建 Agent。");
      await refreshStudioData(nextWorkspace, "");
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "创建工作空间失败。");
    } finally {
      setBusy(false);
    }
  }

  async function createAgent() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      const agent = await apiRequest<Agent>("/agents", {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          org_id: currentWorkspace.orgId,
          team_id: currentWorkspace.teamId,
          name: agentForm.name,
          description: agentForm.description
        }
      });
      setSelectedAgentId(agent.agent_id);
      showToast("success", `Agent「${agent.name}」已创建。`);
      await refreshStudioData(currentWorkspace, agent.agent_id);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "创建 Agent 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function saveWorkspaceFile() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      const agentId = requireAgent();
      await apiRequest(`/agents/${agentId}/workspace/file`, {
        method: "PUT",
        body: {
          actor_user_id: currentWorkspace.userId,
          file_kind: "AGENTS.md",
          content: workspaceText
        }
      });
      showToast("success", "Agent Workspace 已保存。");
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "保存 Workspace 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function saveModelProvider() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      const provider = await apiRequest<ModelProvider>("/model-providers", {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          org_id: currentWorkspace.orgId,
          provider_key: providerForm.providerKey,
          display_name: providerForm.displayName,
          base_url: providerForm.baseUrl,
          api_key: providerForm.apiKey,
          models: providerForm.models.split(",").map((model) => model.trim()).filter(Boolean),
          default_model: providerForm.defaultModel
        }
      });
      showToast("success", `模型供应商「${provider.display_name}」已保存。`);
      await refreshStudioData(currentWorkspace);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "保存模型供应商失败。");
    } finally {
      setBusy(false);
    }
  }

  async function createWorkflow() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      const agentId = requireAgent();
      const workflow = await apiRequest<WorkflowItem>("/workflows", {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          agent_id: agentId,
          name: workflowForm.name,
          description: workflowForm.description,
          draft_definition: workflowDraft
        }
      });
      setSelectedWorkflowId(workflow.workflow_id);
      showToast("success", `Workflow「${workflow.name}」已创建。`);
      await refreshStudioData(currentWorkspace, agentId);
      setSelectedWorkflowId(workflow.workflow_id);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "创建 Workflow 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function saveWorkflowDraft() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      if (!selectedWorkflowId) throw new Error("请先创建或选择 Workflow。");
      await apiRequest<WorkflowItem>(`/workflows/${selectedWorkflowId}/draft`, {
        method: "PUT",
        body: {
          actor_user_id: currentWorkspace.userId,
          draft_definition: workflowDraft
        }
      });
      showToast("success", "Workflow 草稿已保存。");
      await refreshStudioData(currentWorkspace);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "保存 Workflow 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function publishWorkflow() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      if (!selectedWorkflowId) throw new Error("请先创建或选择 Workflow。");
      const version = await apiRequest<WorkflowVersion>(`/workflows/${selectedWorkflowId}/publish`, {
        method: "POST",
        body: { actor_user_id: currentWorkspace.userId }
      });
      setVersions((currentVersions) => [version, ...currentVersions]);
      showToast("success", `Workflow 已发布为 v${version.version_number}。`);
      await refreshStudioData(currentWorkspace);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "发布 Workflow 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function runWorkflow() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      if (!selectedWorkflowId) throw new Error("请先创建或选择 Workflow。");
      const workflow = selectedWorkflow ?? (await apiRequest<WorkflowItem>(`/workflows/${selectedWorkflowId}?actor_user_id=${currentWorkspace.userId}`));
      const versionId = workflow.published_version_id;
      if (!versionId) throw new Error("请先发布 Workflow，再运行。");
      const run = await apiRequest<WorkflowRun>("/workflow-runs", {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          version_id: versionId,
          input_data: { text: workflowForm.input },
          async_mode: false
        }
      });
      setSelectedRunId(run.run_id);
      await loadNodeRuns(run.run_id, currentWorkspace.userId);
      showToast("success", `Workflow 已运行，状态：${run.status}。`);
      await refreshStudioData(currentWorkspace);
      setActiveSection("runs");
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "运行 Workflow 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function createSkill() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      const agentId = requireAgent();
      const skill = await apiRequest<Skill>("/skills", {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          org_id: currentWorkspace.orgId,
          scope: "organization",
          team_id: currentWorkspace.teamId,
          agent_id: agentId,
          content: `---\nname: ${skillForm.name}\ndescription: ${skillForm.description}\n---\n\n优先检查输入、输出、错误处理和运行证据。\n`
        }
      });
      await apiRequest(`/skills/agents/${agentId}/policy`, {
        method: "PUT",
        body: { actor_user_id: currentWorkspace.userId, skill_id: skill.skill_id, allowed: true }
      });
      showToast("success", `Skill「${skill.name}」已创建并授权。`);
      await refreshStudioData(currentWorkspace, agentId);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "创建 Skill 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function createMcpTool() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      const agentId = requireAgent();
      const server = await apiRequest<MCPServer>("/mcp/servers", {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          org_id: currentWorkspace.orgId,
          name: mcpForm.serverName,
          transport: "http",
          url: mcpForm.url
        }
      });
      await apiRequest<MCPTool>(`/mcp/servers/${server.server_id}/tools`, {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          name: mcpForm.toolName,
          description: "检索内部知识库文档。",
          input_schema: { type: "object", properties: { query: { type: "string" } } },
          risk_level: "low"
        }
      });
      await apiRequest(`/mcp/agents/${agentId}/policy`, {
        method: "PUT",
        body: { actor_user_id: currentWorkspace.userId, server_id: server.server_id, allowed: true }
      });
      showToast("success", "MCP Server 和工具已创建并授权。");
      await refreshStudioData(currentWorkspace, agentId);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "创建 MCP 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function createMemory() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      const agentId = requireAgent();
      await apiRequest<MemoryItem>("/memory", {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          agent_id: agentId,
          memory_type: "preference",
          content: memoryForm,
          summary: memoryForm,
          confidence: 0.95,
          source: "studio"
        }
      });
      showToast("success", "Memory 已保存。");
      await refreshStudioData(currentWorkspace, agentId);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "保存 Memory 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function createSessionAndAssembleContext() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      const agentId = requireAgent();
      const session = await apiRequest<SessionItem>("/sessions", {
        method: "POST",
        body: { actor_user_id: currentWorkspace.userId, agent_id: agentId, queue_mode: "queue" }
      });
      await apiRequest(`/sessions/${session.session_id}/messages`, {
        method: "POST",
        body: { actor_user_id: currentWorkspace.userId, role: "user", content: sessionInput }
      });
      const context = await apiRequest<ContextBundle>(
        `/context/sessions/${session.session_id}/assemble?actor_user_id=${currentWorkspace.userId}&current_input=${encodeURIComponent(sessionInput)}&token_budget=4096`
      );
      setContextBundle(context);
      showToast("success", `Context 已组装：${context.sections.length} 个片段。`);
      await refreshStudioData(currentWorkspace, agentId);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "组装 Context 失败。");
    } finally {
      setBusy(false);
    }
  }

  async function generateGatewayPreview() {
    setBusy(true);
    try {
      const currentWorkspace = requireWorkspace();
      await apiRequest("/gateway/llm/generate", {
        method: "POST",
        body: {
          actor_user_id: currentWorkspace.userId,
          org_id: currentWorkspace.orgId,
          provider: selectedProviderKey,
          model: selectedModel,
          prompt: llmNodeForm.prompt,
          parameters: { temperature: Number(llmNodeForm.temperature || 0) }
        }
      });
      const logs = await apiRequest<LLMCallLog[]>("/gateway/llm/logs");
      setGatewayLogs(logs);
      showToast("success", "Gateway 调用完成，日志已更新。");
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "Gateway 调用失败。");
    } finally {
      setBusy(false);
    }
  }

  async function loadNodeRuns(runId: string, actorUserId = workspace?.userId) {
    if (!actorUserId) return;
    const nextNodeRuns = await apiRequest<NodeRun[]>(`/workflow-runs/${runId}/nodes?actor_user_id=${actorUserId}`);
    setNodeRuns(nextNodeRuns);
  }

  return (
    <main className="min-h-screen bg-[#f6f7f9] text-[#172033] lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="border-b border-[#dfe4ee] bg-white p-4 lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#2f6feb] text-white">
            <Network size={19} />
          </div>
          <div>
            <h1 className="text-base font-semibold">AgentFlow Studio</h1>
            <p className="text-xs text-[#667085]">Agent 应用搭建工作台</p>
          </div>
        </div>

        <div className="mb-4 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-[#667085]">API 状态</span>
            <StatusPill status={apiStatus} />
          </div>
          <p className="text-xs leading-5 text-[#667085]">{API_BASE_URL}</p>
        </div>

        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activeSection === item.key;
            return (
              <button
                key={item.key}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition ${
                  active ? "bg-[#eef4ff] font-medium text-[#2f6feb]" : "text-[#344054] hover:bg-[#f8fafc]"
                }`}
                onClick={() => setActiveSection(item.key)}
                type="button"
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className={`mt-5 rounded-lg border p-3 text-sm ${toastClassName(toast.kind)}`}>
          {busy ? <Loader2 className="mr-2 inline animate-spin" size={14} /> : null}
          {toast.text}
        </div>
      </aside>

      <section className="min-w-0 p-4 lg:p-6">
        <header className="mb-5 flex flex-col gap-3 border-b border-[#dfe4ee] pb-5 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h2 className="text-2xl font-semibold">构建一个可运行的 Agent 应用</h2>
            <p className="mt-1 text-sm text-[#667085]">
              创建工作空间，配置 Agent 能力，搭建 Workflow，运行并查看日志。当前数据使用 MVP 内存态后端保存。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="Agents" value={agents.length} />
            <Metric label="Workflows" value={workflows.length} />
            <Metric label="Runs" value={runs.length} />
            <Metric label="Memories" value={memories.length} />
          </div>
        </header>

        {!workspace ? (
          <SetupPanel
            busy={busy}
            form={setupForm}
            onChange={setSetupForm}
            onCreate={createWorkspace}
          />
        ) : (
          <>
            {activeSection === "agents" ? (
              <AgentsPanel
                agentForm={agentForm}
                agents={agents}
                busy={busy}
                mcpTools={mcpTools}
                memories={memories}
                selectedAgent={selectedAgent}
                selectedAgentId={selectedAgentId}
                sessions={sessions}
                skills={skills}
                workspace={workspace}
                workspaceText={workspaceText}
                onAgentFormChange={setAgentForm}
                onCreateAgent={createAgent}
                onSaveWorkspace={saveWorkspaceFile}
                onSelectAgent={setSelectedAgentId}
                onWorkspaceTextChange={setWorkspaceText}
              />
            ) : null}

            {activeSection === "workflow" ? (
              <WorkflowPanel
                busy={busy}
                edges={edges}
                nodes={nodes}
                nodePalette={nodePalette}
                llmNodeForm={llmNodeForm}
                modelOptions={modelOptions}
                modelProviders={modelProviders}
                selectedWorkflowId={selectedWorkflowId}
                selectedModel={selectedModel}
                selectedProviderKey={selectedProviderKey}
                workflowDraft={workflowDraft}
                workflowForm={workflowForm}
                workflows={workflows}
                onAddNode={addNode}
                onConnect={handleConnect}
                onCreateWorkflow={createWorkflow}
                onEdgesChange={onEdgesChange}
                onNodesChange={onNodesChange}
                onPublish={publishWorkflow}
                onRun={runWorkflow}
                onSaveDraft={saveWorkflowDraft}
                onLlmNodeFormChange={setLlmNodeForm}
                onSelectModel={setSelectedModel}
                onSelectProvider={(providerKey) => {
                  setSelectedProviderKey(providerKey);
                  const provider = modelProviders.find((item) => item.provider_key === providerKey);
                  setSelectedModel(provider?.default_model || provider?.models[0] || "mock-model");
                }}
                onSelectWorkflow={setSelectedWorkflowId}
                onWorkflowFormChange={setWorkflowForm}
              />
            ) : null}

            {activeSection === "runtime" ? (
              <RuntimePanel
                busy={busy}
                contextBundle={contextBundle}
                gatewayLogs={gatewayLogs}
                modelProviders={modelProviders}
                mcpForm={mcpForm}
                mcpServers={mcpServers}
                mcpTools={mcpTools}
                memoryForm={memoryForm}
                memories={memories}
                sessionInput={sessionInput}
                sessions={sessions}
                providerForm={providerForm}
                skillForm={skillForm}
                skills={skills}
                onProviderFormChange={setProviderForm}
                onSaveProvider={saveModelProvider}
                onCreateMcp={createMcpTool}
                onCreateMemory={createMemory}
                onCreateSession={createSessionAndAssembleContext}
                onCreateSkill={createSkill}
                onGatewayPreview={generateGatewayPreview}
                onMcpFormChange={setMcpForm}
                onMemoryFormChange={setMemoryForm}
                onSessionInputChange={setSessionInput}
                onSkillFormChange={setSkillForm}
              />
            ) : null}

            {activeSection === "runs" ? (
              <RunsPanel
                nodeRuns={nodeRuns}
                runs={runs}
                selectedRun={selectedRun}
                selectedRunId={selectedRunId}
                versions={versions}
                onLoadNodeRuns={(runId) => {
                  setSelectedRunId(runId);
                  void loadNodeRuns(runId);
                }}
              />
            ) : null}
          </>
        )}
      </section>
    </main>
  );
}

function SetupPanel({
  busy,
  form,
  onChange,
  onCreate
}: {
  busy: boolean;
  form: { email: string; displayName: string; orgName: string; teamName: string };
  onChange: (form: { email: string; displayName: string; orgName: string; teamName: string }) => void;
  onCreate: () => void;
}) {
  return (
    <section className="grid gap-4 lg:grid-cols-[1fr_420px]">
      <div className="rounded-lg border border-[#dfe4ee] bg-white p-5">
        <h3 className="text-lg font-semibold">创建工作空间</h3>
        <p className="mt-1 text-sm text-[#667085]">MVP 阶段会自动创建一个本地用户、组织和团队，用于后续资源隔离。</p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <TextInput label="邮箱" value={form.email} onChange={(email) => onChange({ ...form, email })} />
          <TextInput label="显示名称" value={form.displayName} onChange={(displayName) => onChange({ ...form, displayName })} />
          <TextInput label="组织名称" value={form.orgName} onChange={(orgName) => onChange({ ...form, orgName })} />
          <TextInput label="团队名称" value={form.teamName} onChange={(teamName) => onChange({ ...form, teamName })} />
        </div>
        <button
          className="mt-5 inline-flex items-center gap-2 rounded-md bg-[#2f6feb] px-4 py-2 text-sm font-medium text-white disabled:bg-[#9bb8f5]"
          disabled={busy}
          onClick={onCreate}
          type="button"
        >
          {busy ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />}
          创建并进入 Studio
        </button>
      </div>
      <div className="rounded-lg border border-[#dfe4ee] bg-[#0f172a] p-5 text-[#dbeafe]">
        <h3 className="text-sm font-semibold text-white">接下来你可以做什么</h3>
        <ol className="mt-4 space-y-3 text-sm leading-6">
          <li>1. 创建 Agent 并编辑 AGENTS.md 工作区指令。</li>
          <li>2. 注册 Skill、MCP Tool、Memory 和 Session 上下文。</li>
          <li>3. 在画布中搭建 Workflow，保存、发布并运行。</li>
          <li>4. 查看 Run、Node Run、Gateway Log 和输出结果。</li>
        </ol>
      </div>
    </section>
  );
}

function AgentsPanel(props: {
  agentForm: { name: string; description: string };
  agents: Agent[];
  busy: boolean;
  mcpTools: MCPTool[];
  memories: MemoryItem[];
  selectedAgent: Agent | null;
  selectedAgentId: string;
  sessions: SessionItem[];
  skills: Skill[];
  workspace: WorkspaceState;
  workspaceText: string;
  onAgentFormChange: (form: { name: string; description: string }) => void;
  onCreateAgent: () => void;
  onSaveWorkspace: () => void;
  onSelectAgent: (agentId: string) => void;
  onWorkspaceTextChange: (text: string) => void;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <section className="space-y-4">
        <Panel title="创建 Agent" icon={Bot}>
          <div className="space-y-3">
            <TextInput label="名称" value={props.agentForm.name} onChange={(name) => props.onAgentFormChange({ ...props.agentForm, name })} />
            <TextArea
              label="描述"
              rows={4}
              value={props.agentForm.description}
              onChange={(description) => props.onAgentFormChange({ ...props.agentForm, description })}
            />
            <PrimaryButton busy={props.busy} label="创建 Agent" onClick={props.onCreateAgent} />
          </div>
        </Panel>
        <Panel title="Agent 列表" icon={Network}>
          <div className="space-y-2">
            {props.agents.length === 0 ? <EmptyText text="暂无 Agent。" /> : null}
            {props.agents.map((agent) => (
              <button
                key={agent.agent_id}
                className={`w-full rounded-md border p-3 text-left text-sm ${
                  props.selectedAgentId === agent.agent_id ? "border-[#2f6feb] bg-[#eef4ff]" : "border-[#dfe4ee] bg-white"
                }`}
                onClick={() => props.onSelectAgent(agent.agent_id)}
                type="button"
              >
                <div className="font-medium">{agent.name}</div>
                <div className="mt-1 text-xs text-[#667085]">{agent.description}</div>
              </button>
            ))}
          </div>
        </Panel>
      </section>

      <section className="space-y-4">
        <Panel title="Agent Workspace" icon={FileText}>
          <div className="mb-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Skills" value={props.skills.length} />
            <Metric label="MCP Tools" value={props.mcpTools.length} />
            <Metric label="Memories" value={props.memories.length} />
            <Metric label="Sessions" value={props.sessions.length} />
          </div>
          <TextArea label="AGENTS.md" rows={12} value={props.workspaceText} onChange={props.onWorkspaceTextChange} />
          <div className="mt-3 flex items-center justify-between text-xs text-[#667085]">
            <span>当前组织：{props.workspace.orgId}</span>
            <button className="rounded-md bg-[#2f6feb] px-3 py-2 text-sm font-medium text-white" onClick={props.onSaveWorkspace} type="button">
              保存 Workspace
            </button>
          </div>
        </Panel>
      </section>
    </div>
  );
}

function WorkflowPanel(props: {
  busy: boolean;
  edges: Edge[];
  llmNodeForm: { systemPrompt: string; prompt: string; temperature: string };
  modelOptions: string[];
  modelProviders: ModelProvider[];
  nodes: Node[];
  nodePalette: typeof nodePalette;
  selectedModel: string;
  selectedProviderKey: string;
  selectedWorkflowId: string;
  workflowDraft: Record<string, unknown>;
  workflowForm: { name: string; description: string; input: string };
  workflows: WorkflowItem[];
  onAddNode: (label: string) => void;
  onConnect: (connection: Connection) => void;
  onCreateWorkflow: () => void;
  onEdgesChange: ReturnType<typeof useEdgesState>[2];
  onLlmNodeFormChange: (form: { systemPrompt: string; prompt: string; temperature: string }) => void;
  onNodesChange: ReturnType<typeof useNodesState>[2];
  onPublish: () => void;
  onRun: () => void;
  onSaveDraft: () => void;
  onSelectModel: (model: string) => void;
  onSelectProvider: (providerKey: string) => void;
  onSelectWorkflow: (workflowId: string) => void;
  onWorkflowFormChange: (form: { name: string; description: string; input: string }) => void;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
      <section className="space-y-4">
        <div className="h-[560px] overflow-hidden rounded-lg border border-[#dfe4ee] bg-white">
          <div className="border-b border-[#dfe4ee] px-4 py-3">
            <h3 className="text-sm font-semibold">Workflow 画布</h3>
            <p className="mt-1 text-xs text-[#667085]">拖拽节点、连线，然后保存草稿、发布并运行。</p>
          </div>
          <ReactFlow
            edges={props.edges}
            fitView
            nodes={props.nodes}
            onConnect={props.onConnect}
            onEdgesChange={props.onEdgesChange}
            onNodesChange={props.onNodesChange}
          >
            <Background color="#d9e0ec" gap={18} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>
      </section>

      <section className="space-y-4">
        <Panel title="Workflow 配置" icon={Workflow}>
          <div className="space-y-3">
            <TextInput label="名称" value={props.workflowForm.name} onChange={(name) => props.onWorkflowFormChange({ ...props.workflowForm, name })} />
            <TextArea
              label="描述"
              rows={3}
              value={props.workflowForm.description}
              onChange={(description) => props.onWorkflowFormChange({ ...props.workflowForm, description })}
            />
            <TextArea
              label="运行输入"
              rows={4}
              value={props.workflowForm.input}
              onChange={(input) => props.onWorkflowFormChange({ ...props.workflowForm, input })}
            />
            <div className="rounded-md border border-[#dfe4ee] bg-[#f8fafc] p-3">
              <div className="mb-3 text-xs font-semibold text-[#344054]">LLM 节点模型</div>
              <div className="grid gap-2 sm:grid-cols-2">
                <SelectInput
                  label="供应商"
                  value={props.selectedProviderKey}
                  options={[
                    { label: "Mock / 本地测试", value: "mock" },
                    ...props.modelProviders.map((provider) => ({
                      label: provider.display_name,
                      value: provider.provider_key
                    }))
                  ]}
                  onChange={props.onSelectProvider}
                />
                <SelectInput
                  label="模型"
                  value={props.selectedModel}
                  options={props.modelOptions.map((model) => ({ label: model, value: model }))}
                  onChange={props.onSelectModel}
                />
              </div>
              <TextArea
                label="系统提示词"
                rows={3}
                value={props.llmNodeForm.systemPrompt}
                onChange={(systemPrompt) => props.onLlmNodeFormChange({ ...props.llmNodeForm, systemPrompt })}
              />
              <TextArea
                label="节点提示词"
                rows={3}
                value={props.llmNodeForm.prompt}
                onChange={(prompt) => props.onLlmNodeFormChange({ ...props.llmNodeForm, prompt })}
              />
              <TextInput
                label="Temperature"
                value={props.llmNodeForm.temperature}
                onChange={(temperature) => props.onLlmNodeFormChange({ ...props.llmNodeForm, temperature })}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              {props.nodePalette.map((item) => (
                <button
                  key={item.label}
                  className="rounded-md border border-[#dfe4ee] bg-white px-3 py-2 text-left text-sm hover:border-[#2f6feb]"
                  onClick={() => props.onAddNode(item.label)}
                  type="button"
                >
                  添加 {item.label}
                </button>
              ))}
            </div>
            <PrimaryButton busy={props.busy} label="创建 Workflow" onClick={props.onCreateWorkflow} />
            <div className="grid grid-cols-3 gap-2">
              <SecondaryButton label="保存" onClick={props.onSaveDraft} />
              <SecondaryButton label="发布" onClick={props.onPublish} />
              <SecondaryButton label="运行" onClick={props.onRun} />
            </div>
          </div>
        </Panel>

        <Panel title="Workflow 列表" icon={GitBranch}>
          <div className="space-y-2">
            {props.workflows.length === 0 ? <EmptyText text="暂无 Workflow。" /> : null}
            {props.workflows.map((workflow) => (
              <button
                key={workflow.workflow_id}
                className={`w-full rounded-md border p-3 text-left text-sm ${
                  props.selectedWorkflowId === workflow.workflow_id ? "border-[#2f6feb] bg-[#eef4ff]" : "border-[#dfe4ee] bg-white"
                }`}
                onClick={() => props.onSelectWorkflow(workflow.workflow_id)}
                type="button"
              >
                <div className="font-medium">{workflow.name}</div>
                <div className="mt-1 text-xs text-[#667085]">{workflow.published_version_id ? "已发布" : "草稿"}</div>
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="DSL 预览" icon={FileText}>
          <pre className="max-h-[220px] overflow-auto rounded-md bg-[#0f172a] p-3 text-xs leading-5 text-[#dbeafe]">
            {JSON.stringify(props.workflowDraft, null, 2)}
          </pre>
        </Panel>
      </section>
    </div>
  );
}

function RuntimePanel(props: {
  busy: boolean;
  contextBundle: ContextBundle | null;
  gatewayLogs: LLMCallLog[];
  modelProviders: ModelProvider[];
  mcpForm: { serverName: string; url: string; toolName: string };
  mcpServers: MCPServer[];
  mcpTools: MCPTool[];
  memoryForm: string;
  memories: MemoryItem[];
  sessionInput: string;
  sessions: SessionItem[];
  providerForm: { providerKey: string; displayName: string; baseUrl: string; apiKey: string; models: string; defaultModel: string };
  skillForm: { name: string; description: string };
  skills: Skill[];
  onCreateMcp: () => void;
  onCreateMemory: () => void;
  onCreateSession: () => void;
  onCreateSkill: () => void;
  onGatewayPreview: () => void;
  onMcpFormChange: (form: { serverName: string; url: string; toolName: string }) => void;
  onMemoryFormChange: (text: string) => void;
  onProviderFormChange: (form: { providerKey: string; displayName: string; baseUrl: string; apiKey: string; models: string; defaultModel: string }) => void;
  onSaveProvider: () => void;
  onSessionInputChange: (text: string) => void;
  onSkillFormChange: (form: { name: string; description: string }) => void;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="Model Providers" icon={Bot}>
        <div className="grid gap-2 sm:grid-cols-2">
          <TextInput label="Provider Key" value={props.providerForm.providerKey} onChange={(providerKey) => props.onProviderFormChange({ ...props.providerForm, providerKey })} />
          <TextInput label="显示名称" value={props.providerForm.displayName} onChange={(displayName) => props.onProviderFormChange({ ...props.providerForm, displayName })} />
        </div>
        <TextInput label="Base URL" value={props.providerForm.baseUrl} onChange={(baseUrl) => props.onProviderFormChange({ ...props.providerForm, baseUrl })} />
        <TextInput label="API Key" value={props.providerForm.apiKey} onChange={(apiKey) => props.onProviderFormChange({ ...props.providerForm, apiKey })} />
        <TextInput label="模型列表" value={props.providerForm.models} onChange={(models) => props.onProviderFormChange({ ...props.providerForm, models })} />
        <TextInput label="默认模型" value={props.providerForm.defaultModel} onChange={(defaultModel) => props.onProviderFormChange({ ...props.providerForm, defaultModel })} />
        <PrimaryButton busy={props.busy} label="保存模型供应商" onClick={props.onSaveProvider} />
        <ResourceList items={props.modelProviders.map((provider) => `${provider.display_name} · ${provider.provider_key} · ${provider.api_key_masked || "no-key"}`)} />
      </Panel>

      <Panel title="Skill Registry" icon={Brain}>
        <TextInput label="Skill 名称" value={props.skillForm.name} onChange={(name) => props.onSkillFormChange({ ...props.skillForm, name })} />
        <TextInput
          label="说明"
          value={props.skillForm.description}
          onChange={(description) => props.onSkillFormChange({ ...props.skillForm, description })}
        />
        <PrimaryButton busy={props.busy} label="创建并授权 Skill" onClick={props.onCreateSkill} />
        <ResourceList items={props.skills.map((skill) => `${skill.name} · ${skill.description}`)} />
      </Panel>

      <Panel title="MCP Tools" icon={Server}>
        <TextInput label="Server 名称" value={props.mcpForm.serverName} onChange={(serverName) => props.onMcpFormChange({ ...props.mcpForm, serverName })} />
        <TextInput label="URL" value={props.mcpForm.url} onChange={(url) => props.onMcpFormChange({ ...props.mcpForm, url })} />
        <TextInput label="Tool 名称" value={props.mcpForm.toolName} onChange={(toolName) => props.onMcpFormChange({ ...props.mcpForm, toolName })} />
        <PrimaryButton busy={props.busy} label="创建 MCP Tool" onClick={props.onCreateMcp} />
        <ResourceList items={[...props.mcpServers.map((server) => `Server: ${server.name}`), ...props.mcpTools.map((tool) => `Tool: ${tool.name}`)]} />
      </Panel>

      <Panel title="Memory" icon={Database}>
        <TextArea label="长期记忆" rows={4} value={props.memoryForm} onChange={props.onMemoryFormChange} />
        <PrimaryButton busy={props.busy} label="保存 Memory" onClick={props.onCreateMemory} />
        <ResourceList items={props.memories.map((memory) => `${memory.memory_type} · ${memory.summary}`)} />
      </Panel>

      <Panel title="Session / Context" icon={MessageSquare}>
        <TextArea label="用户消息" rows={4} value={props.sessionInput} onChange={props.onSessionInputChange} />
        <PrimaryButton busy={props.busy} label="创建 Session 并组装 Context" onClick={props.onCreateSession} />
        <div className="mt-3 grid grid-cols-2 gap-2">
          <Metric label="Sessions" value={props.sessions.length} />
          <Metric label="Context Sections" value={props.contextBundle?.sections.length ?? 0} />
        </div>
      </Panel>

      <Panel title="Gateway" icon={ShieldCheck}>
        <p className="mb-3 text-sm leading-6 text-[#667085]">通过统一网关调用 Mock LLM，并查看 prefix hash 与调用日志。</p>
        <PrimaryButton busy={props.busy} label="生成预览回复" onClick={props.onGatewayPreview} />
        <ResourceList items={props.gatewayLogs.slice(0, 5).map((log) => `${log.status} · ${log.provider}/${log.model} · ${log.prefix_hash || "no-prefix"}`)} />
      </Panel>
    </div>
  );
}

function RunsPanel(props: {
  nodeRuns: NodeRun[];
  runs: WorkflowRun[];
  selectedRun: WorkflowRun | null;
  selectedRunId: string;
  versions: WorkflowVersion[];
  onLoadNodeRuns: (runId: string) => void;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <Panel title="运行历史" icon={Activity}>
        <div className="space-y-2">
          {props.runs.length === 0 ? <EmptyText text="暂无运行记录。请先发布并运行 Workflow。" /> : null}
          {props.runs.map((run) => (
            <button
              key={run.run_id}
              className={`w-full rounded-md border p-3 text-left text-sm ${
                props.selectedRunId === run.run_id ? "border-[#2f6feb] bg-[#eef4ff]" : "border-[#dfe4ee] bg-white"
              }`}
              onClick={() => props.onLoadNodeRuns(run.run_id)}
              type="button"
            >
              <div className="font-mono text-xs">{run.run_id}</div>
              <div className="mt-1 text-xs text-[#667085]">状态：{run.status}</div>
            </button>
          ))}
        </div>
      </Panel>

      <section className="space-y-4">
        <Panel title="运行详情" icon={CheckCircle2}>
          {props.selectedRun ? (
            <pre className="max-h-[320px] overflow-auto rounded-md bg-[#0f172a] p-3 text-xs leading-5 text-[#dbeafe]">
              {JSON.stringify(props.selectedRun.output_data, null, 2)}
            </pre>
          ) : (
            <EmptyText text="选择一次运行后查看输出。" />
          )}
        </Panel>
        <Panel title="节点日志" icon={GitBranch}>
          <div className="grid gap-2 md:grid-cols-3">
            {props.nodeRuns.map((nodeRun) => (
              <div key={nodeRun.node_run_id} className="rounded-md border border-[#dfe4ee] bg-white p-3 text-sm">
                <div className="font-medium">{nodeRun.node_id}</div>
                <div className="mt-1 text-xs text-[#667085]">{nodeRun.node_type} · {nodeRun.status} · {nodeRun.elapsed_ms}ms</div>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="发布版本" icon={FileText}>
          <ResourceList items={props.versions.map((version) => `v${version.version_number} · ${version.version_id}`)} />
        </Panel>
      </section>
    </div>
  );
}

function Panel({ children, icon: Icon, title }: { children: React.ReactNode; icon: typeof Bot; title: string }) {
  return (
    <section className="rounded-lg border border-[#dfe4ee] bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Icon size={17} className="text-[#2f6feb]" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function TextInput({ label, onChange, value }: { label: string; onChange: (value: string) => void; value: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-[#667085]">{label}</span>
      <input
        className="w-full rounded-md border border-[#dfe4ee] bg-white px-3 py-2 text-sm outline-none focus:border-[#2f6feb]"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </label>
  );
}

function SelectInput({
  label,
  onChange,
  options,
  value
}: {
  label: string;
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
  value: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-[#667085]">{label}</span>
      <select
        className="w-full rounded-md border border-[#dfe4ee] bg-white px-3 py-2 text-sm outline-none focus:border-[#2f6feb]"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function TextArea({ label, onChange, rows, value }: { label: string; onChange: (value: string) => void; rows: number; value: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-[#667085]">{label}</span>
      <textarea
        className="w-full resize-y rounded-md border border-[#dfe4ee] bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-[#2f6feb]"
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        value={value}
      />
    </label>
  );
}

function PrimaryButton({ busy, label, onClick }: { busy: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className="mt-3 inline-flex items-center gap-2 rounded-md bg-[#2f6feb] px-3 py-2 text-sm font-medium text-white disabled:bg-[#9bb8f5]"
      disabled={busy}
      onClick={onClick}
      type="button"
    >
      {busy ? <Loader2 className="animate-spin" size={15} /> : <Plus size={15} />}
      {label}
    </button>
  );
}

function SecondaryButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button className="rounded-md border border-[#cfd7e6] bg-white px-3 py-2 text-sm font-medium hover:border-[#2f6feb]" onClick={onClick} type="button">
      {label}
    </button>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-[#dfe4ee] bg-white px-3 py-2">
      <div className="text-xs text-[#667085]">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}

function ResourceList({ items }: { items: string[] }) {
  if (items.length === 0) return <EmptyText text="暂无数据。" />;
  return (
    <ul className="mt-3 space-y-2">
      {items.map((item) => (
        <li key={item} className="overflow-hidden text-ellipsis whitespace-nowrap rounded-md border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2 text-sm">
          {item}
        </li>
      ))}
    </ul>
  );
}

function EmptyText({ text }: { text: string }) {
  return <p className="rounded-md border border-dashed border-[#dfe4ee] bg-[#f8fafc] px-3 py-3 text-sm text-[#667085]">{text}</p>;
}

function StatusPill({ status }: { status: ApiStatus }) {
  const statusText = { checking: "检测中", online: "在线", offline: "离线" }[status];
  const statusClassName = {
    checking: "bg-[#fff7ed] text-[#c2410c]",
    online: "bg-[#ecfdf3] text-[#027a48]",
    offline: "bg-[#fef3f2] text-[#b42318]"
  }[status];
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusClassName}`}>{statusText}</span>;
}

function toastClassName(kind: ToastKind) {
  if (kind === "success") return "border-[#bbf7d0] bg-[#f0fdf4] text-[#047857]";
  if (kind === "error") return "border-[#fecaca] bg-[#fef2f2] text-[#b42318]";
  return "border-[#dfe4ee] bg-[#f8fafc] text-[#344054]";
}

async function apiRequest<T>(path: string, options: { method?: string; body?: object } = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      detail = formatApiErrorDetail(payload.detail) ?? detail;
    } catch {
      detail = response.statusText;
    }
    throw new Error(`请求失败：${detail}`);
  }

  return (await response.json()) as T;
}

function formatApiErrorDetail(detail: ApiErrorPayload["detail"]): string | undefined {
  if (!detail) return undefined;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg ?? JSON.stringify(item)).join("；");
  return detail.msg ?? JSON.stringify(detail);
}
