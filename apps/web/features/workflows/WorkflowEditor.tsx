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
  CheckCircle2,
  CircleDot,
  Clock3,
  Database,
  FileText,
  GitBranch,
  Loader2,
  Network,
  Play,
  Save,
  Server,
  ShieldCheck,
  Workflow,
  XCircle
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type ApiStatus = "checking" | "online" | "offline";
type StepStatus = "idle" | "running" | "success" | "failed";

type IntegrationStep = {
  key: string;
  title: string;
  description: string;
  status: StepStatus;
  detail: string;
};

type IntegrationState = {
  userId: string;
  viewerId: string;
  orgId: string;
  teamId: string;
  agentId: string;
  sessionId: string;
  skillId: string;
  mcpServerId: string;
  mcpToolId: string;
  memoryId: string;
  workflowId: string;
  versionId: string;
  runId: string;
  runStatus: string;
  nodeRunCount: number;
  gatewayLogCount: number;
  auditLogCount: number;
  contextSectionCount: number;
  outputPreview: string;
};

type ApiErrorPayload = {
  detail?: string | { msg?: string } | Array<{ msg?: string }>;
};

type IdResponse<Key extends string> = Record<Key, string>;

type WorkflowResponse = {
  workflow_id: string;
  published_version_id: string | null;
};

type WorkflowVersionResponse = {
  version_id: string;
  version_number: number;
};

type WorkflowRunResponse = {
  run_id: string;
  status: string;
  output_data: Record<string, unknown>;
};

type NodeRunResponse = {
  node_run_id: string;
  status: string;
};

type ContextBundle = {
  sections: Array<{ name: string; content: string; estimated_tokens: number }>;
  total_estimated_tokens: number;
  need_compaction: boolean;
};

type LLMCallLogResponse = {
  call_id: string;
  status: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const initialNodes: Node[] = [
  {
    id: "start",
    type: "default",
    position: { x: 70, y: 180 },
    data: { label: "Start" }
  },
  {
    id: "llm",
    type: "default",
    position: { x: 360, y: 180 },
    data: { label: "LLM" }
  },
  {
    id: "end",
    type: "default",
    position: { x: 650, y: 180 },
    data: { label: "End" }
  }
];

const initialEdges: Edge[] = [
  { id: "start-llm", source: "start", target: "llm" },
  { id: "llm-end", source: "llm", target: "end" }
];

const nodePalette = [
  { label: "LLM", description: "模型推理节点", icon: Bot },
  { label: "RAG", description: "知识检索占位", icon: Database },
  { label: "Tool", description: "工具调用占位", icon: ShieldCheck }
];

const initialIntegrationSteps: IntegrationStep[] = [
  { key: "health", title: "API 健康检查", description: "确认 FastAPI 可访问", status: "idle", detail: "等待执行" },
  { key: "identity", title: "用户与组织", description: "注册用户、组织、团队和成员", status: "idle", detail: "等待执行" },
  { key: "agent", title: "Agent Workspace", description: "创建 Agent 并写入 Workspace", status: "idle", detail: "等待执行" },
  { key: "session", title: "Session 与消息", description: "创建会话、追加消息、压缩摘要", status: "idle", detail: "等待执行" },
  { key: "skill", title: "Skill Registry", description: "注册 Skill、授权并读取摘要", status: "idle", detail: "等待执行" },
  { key: "mcp", title: "MCP Registry", description: "注册 MCP Server、Tool 和授权策略", status: "idle", detail: "等待执行" },
  { key: "memory", title: "Memory Manager", description: "写入记忆并按关键词召回", status: "idle", detail: "等待执行" },
  { key: "context", title: "Context Engine", description: "组合 Workspace、消息、Skill 和 Memory", status: "idle", detail: "等待执行" },
  { key: "gateway", title: "Gateway + LLM", description: "通过统一网关调用 Mock LLM 并读取日志", status: "idle", detail: "等待执行" },
  { key: "workflow", title: "Workflow 执行", description: "创建、发布、运行并读取节点日志", status: "idle", detail: "等待执行" },
  { key: "rbac", title: "权限隔离", description: "验证 viewer 无法创建受限资源", status: "idle", detail: "等待执行" },
  { key: "audit", title: "审计日志", description: "读取组织审计事件", status: "idle", detail: "等待执行" }
];

export default function WorkflowEditor() {
  // nodes 保存画布节点状态，React Flow 在拖拽和选择时更新它。
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);

  // edges 保存节点连线状态，用于生成后端 Workflow DSL。
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // selectedNodeId 保存右侧属性面板当前展示的节点 ID。
  const [selectedNodeId, setSelectedNodeId] = useState<string>("llm");

  // apiStatus 表示前端到 FastAPI 服务的健康检查结果。
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");

  // busy 表示当前是否有保存、发布或联调运行请求。
  const [busy, setBusy] = useState(false);

  // message 保存用户可见的当前操作反馈。
  const [message, setMessage] = useState("准备就绪，点击一键全链路联调即可覆盖主要后端模块。");

  // integrationSteps 保存全链路联调每个后端模块的执行状态。
  const [integrationSteps, setIntegrationSteps] = useState<IntegrationStep[]>(initialIntegrationSteps);

  // integrationState 保存本轮联调生成的后端资源 ID 和关键结果。
  const [integrationState, setIntegrationState] = useState<IntegrationState | null>(null);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId);

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
            provider: label === "LLM" ? "mock" : undefined,
            model: label === "LLM" ? "mock-model" : undefined,
            prompt: label === "LLM" ? "请总结输入，并给出下一步建议。" : undefined
          }
        };
      }),
      edges: edges.map((edge) => ({
        source: edge.source,
        target: edge.target
      }))
    };
  }, [nodes, edges]);

  useEffect(() => {
    let isMounted = true;

    async function checkHealth() {
      try {
        const health = await apiRequest<{ status: string }>("/health");
        if (isMounted) {
          setApiStatus(health.status === "ok" ? "online" : "offline");
        }
      } catch {
        if (isMounted) {
          setApiStatus("offline");
        }
      }
    }

    void checkHealth();

    return () => {
      isMounted = false;
    };
  }, []);

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

  function updateStep(key: string, status: StepStatus, detail: string) {
    setIntegrationSteps((currentSteps) =>
      currentSteps.map((step) => (step.key === key ? { ...step, status, detail } : step))
    );
  }

  async function runFullIntegration() {
    setBusy(true);
    setIntegrationState(null);
    setIntegrationSteps(initialIntegrationSteps);
    setMessage("正在执行完整前后端联调...");

    try {
      updateStep("health", "running", "正在请求 /health");
      const health = await apiRequest<{ status: string }>("/health");
      updateStep("health", "success", `API 状态：${health.status}`);

      updateStep("identity", "running", "正在创建用户、组织、团队和成员");
      const timestamp = Date.now();
      const owner = await apiRequest<IdResponse<"user_id">>("/identity/users/register", {
        method: "POST",
        body: {
          email: `owner-${timestamp}@example.com`,
          display_name: "平台管理员",
          password: "password123"
        }
      });
      const viewer = await apiRequest<IdResponse<"user_id">>("/identity/users/register", {
        method: "POST",
        body: {
          email: `viewer-${timestamp}@example.com`,
          display_name: "只读成员",
          password: "password123"
        }
      });
      const organization = await apiRequest<IdResponse<"org_id">>("/identity/organizations", {
        method: "POST",
        body: {
          creator_user_id: owner.user_id,
          name: "AgentFlow 全链路组织"
        }
      });
      const team = await apiRequest<IdResponse<"team_id">>(`/identity/organizations/${organization.org_id}/teams`, {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          name: "研发联调组"
        }
      });
      await apiRequest("/identity/organizations/" + organization.org_id + "/members", {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          target_user_id: viewer.user_id,
          role: "viewer",
          team_ids: [team.team_id]
        }
      });
      updateStep("identity", "success", `组织 ${organization.org_id}，团队 ${team.team_id}`);

      updateStep("agent", "running", "正在创建 Agent 并更新 Workspace");
      const agent = await apiRequest<IdResponse<"agent_id">>("/agents", {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          org_id: organization.org_id,
          team_id: team.team_id,
          name: "全链路联调 Agent",
          description: "用于验证用户、运行时、上下文、Skill、MCP、Memory、Gateway 与 Workflow。"
        }
      });
      await apiRequest(`/agents/${agent.agent_id}/workspace/file`, {
        method: "PUT",
        body: {
          actor_user_id: owner.user_id,
          file_kind: "AGENTS.md",
          content: "# AGENTS\n\n你是全链路联调 Agent。回答时优先给结论，并使用中文。\n"
        }
      });
      await apiRequest(`/agents/${agent.agent_id}/workspace?actor_user_id=${owner.user_id}`);
      await apiRequest(`/agents?org_id=${organization.org_id}&actor_user_id=${owner.user_id}`);
      updateStep("agent", "success", `Agent ${agent.agent_id} 已创建`);

      updateStep("session", "running", "正在创建 Session、追加消息和压缩摘要");
      const session = await apiRequest<IdResponse<"session_id">>("/sessions", {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          agent_id: agent.agent_id,
          queue_mode: "queue"
        }
      });
      const messageResponse = await apiRequest<IdResponse<"message_id">>(`/sessions/${session.session_id}/messages`, {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          role: "user",
          content: "请使用 Skill、MCP、Memory 和 Workflow 完成一次全链路验证。"
        }
      });
      await apiRequest(`/sessions/${session.session_id}/compact`, {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          summary: "用户要求完成一次完整前后端联调验证。"
        }
      });
      await apiRequest(`/sessions/${session.session_id}/messages?actor_user_id=${owner.user_id}`);
      updateStep("session", "success", `Session ${session.session_id}，消息 ${messageResponse.message_id}`);

      updateStep("skill", "running", "正在注册 Skill 并授权给 Agent");
      const skill = await apiRequest<IdResponse<"skill_id">>("/skills", {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          org_id: organization.org_id,
          scope: "organization",
          content:
            "---\nname: workflow-reviewer\ndescription: 检查工作流结构并给出改进建议\n---\n\n优先检查节点顺序、输入输出和错误处理。\n",
          team_id: team.team_id,
          agent_id: agent.agent_id
        }
      });
      await apiRequest(`/skills/agents/${agent.agent_id}/policy`, {
        method: "PUT",
        body: {
          actor_user_id: owner.user_id,
          skill_id: skill.skill_id,
          allowed: true
        }
      });
      const skillSummaries = await apiRequest<Array<Record<string, string>>>(
        `/skills/agents/${agent.agent_id}/summaries?actor_user_id=${owner.user_id}`
      );
      await apiRequest(`/skills/agents/${agent.agent_id}/skills/${skill.skill_id}?actor_user_id=${owner.user_id}`);
      updateStep("skill", "success", `已授权 ${skillSummaries.length} 个 Skill`);

      updateStep("mcp", "running", "正在注册 MCP Server、Tool 和授权策略");
      const mcpServer = await apiRequest<IdResponse<"server_id">>("/mcp/servers", {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          org_id: organization.org_id,
          name: "知识库 MCP",
          transport: "http",
          url: "http://localhost:18080/mcp"
        }
      });
      const mcpTool = await apiRequest<IdResponse<"tool_id">>(`/mcp/servers/${mcpServer.server_id}/tools`, {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          name: "search_docs",
          description: "检索内部知识库文档",
          input_schema: {
            type: "object",
            properties: {
              query: { type: "string" }
            }
          },
          risk_level: "low"
        }
      });
      await apiRequest(`/mcp/agents/${agent.agent_id}/policy`, {
        method: "PUT",
        body: {
          actor_user_id: owner.user_id,
          server_id: mcpServer.server_id,
          allowed: true
        }
      });
      await apiRequest(`/mcp/agents/${agent.agent_id}/tools?actor_user_id=${owner.user_id}`);
      await apiRequest(`/mcp/agents/${agent.agent_id}/tools/${mcpTool.tool_id}/can-call?actor_user_id=${owner.user_id}`);
      updateStep("mcp", "success", `Tool ${mcpTool.tool_id} 可调用`);

      updateStep("memory", "running", "正在写入和召回 Agent 记忆");
      const memory = await apiRequest<IdResponse<"memory_id">>("/memory", {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          agent_id: agent.agent_id,
          memory_type: "preference",
          content: "用户偏好中文、先给结论、再给验证证据。",
          summary: "用户偏好中文并先给结论。",
          confidence: 0.98,
          source: "frontend-integration"
        }
      });
      const recalledMemories = await apiRequest<Array<Record<string, string>>>("/memory/recall", {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          agent_id: agent.agent_id,
          query: "中文 结论",
          limit: 5
        }
      });
      updateStep("memory", "success", `召回 ${recalledMemories.length} 条记忆`);

      updateStep("context", "running", "正在组装 Session 上下文");
      const contextBundle = await apiRequest<ContextBundle>(
        `/context/sessions/${session.session_id}/assemble?actor_user_id=${owner.user_id}&current_input=${encodeURIComponent(
          "请输出完整联调报告"
        )}&token_budget=4096`
      );
      updateStep("context", "success", `上下文 ${contextBundle.sections.length} 段，约 ${contextBundle.total_estimated_tokens} tokens`);

      updateStep("gateway", "running", "正在调用 Gateway LLM 并读取日志");
      await apiRequest("/gateway/llm/generate", {
        method: "POST",
        body: {
          provider: "mock",
          model: "mock-model",
          prompt: "请用一句话总结全链路联调状态。",
          parameters: { temperature: 0 }
        }
      });
      const gatewayLogs = await apiRequest<LLMCallLogResponse[]>("/gateway/llm/logs");
      updateStep("gateway", "success", `Gateway 日志 ${gatewayLogs.length} 条`);

      updateStep("workflow", "running", "正在创建、发布、运行 Workflow");
      const workflow = await saveWorkflow(owner.user_id, agent.agent_id);
      const version = await publishWorkflow(owner.user_id, workflow.workflow_id);
      const versions = await apiRequest<WorkflowVersionResponse[]>(
        `/workflows/${workflow.workflow_id}/versions?actor_user_id=${owner.user_id}`
      );
      const run = await apiRequest<WorkflowRunResponse>("/workflow-runs", {
        method: "POST",
        body: {
          actor_user_id: owner.user_id,
          version_id: version.version_id,
          input_data: {
            text: "请验证完整前后端联调链路，并输出简洁总结。"
          },
          async_mode: false
        }
      });
      const runDetail = await apiRequest<WorkflowRunResponse>(`/workflow-runs/${run.run_id}?actor_user_id=${owner.user_id}`);
      const nodeRuns = await apiRequest<NodeRunResponse[]>(`/workflow-runs/${run.run_id}/nodes?actor_user_id=${owner.user_id}`);
      updateStep("workflow", "success", `版本 ${versions.length} 个，节点日志 ${nodeRuns.length} 条，状态 ${runDetail.status}`);

      updateStep("rbac", "running", "正在验证 viewer 权限限制");
      const forbiddenResult = await apiRequestExpectError("/agents", {
        method: "POST",
        body: {
          actor_user_id: viewer.user_id,
          org_id: organization.org_id,
          name: "非法 Agent",
          description: "viewer 不应创建该资源。"
        }
      });
      if (forbiddenResult.status !== 403) {
        throw new Error(`权限测试失败：预期 403，实际 ${forbiddenResult.status}`);
      }
      updateStep("rbac", "success", "viewer 创建 Agent 被正确拒绝");

      updateStep("audit", "running", "正在读取组织审计日志");
      const auditLogs = await apiRequest<Array<Record<string, unknown>>>(
        `/identity/organizations/${organization.org_id}/audit-logs?actor_user_id=${owner.user_id}`
      );
      updateStep("audit", "success", `审计日志 ${auditLogs.length} 条`);

      setIntegrationState({
        userId: owner.user_id,
        viewerId: viewer.user_id,
        orgId: organization.org_id,
        teamId: team.team_id,
        agentId: agent.agent_id,
        sessionId: session.session_id,
        skillId: skill.skill_id,
        mcpServerId: mcpServer.server_id,
        mcpToolId: mcpTool.tool_id,
        memoryId: memory.memory_id,
        workflowId: workflow.workflow_id,
        versionId: version.version_id,
        runId: run.run_id,
        runStatus: runDetail.status,
        nodeRunCount: nodeRuns.length,
        gatewayLogCount: gatewayLogs.length,
        auditLogCount: auditLogs.length,
        contextSectionCount: contextBundle.sections.length,
        outputPreview: JSON.stringify(
          {
            context: {
              sections: contextBundle.sections.map((section) => section.name),
              total_estimated_tokens: contextBundle.total_estimated_tokens,
              need_compaction: contextBundle.need_compaction
            },
            workflow_output: runDetail.output_data,
            node_runs: nodeRuns.map((nodeRun) => ({ id: nodeRun.node_run_id, status: nodeRun.status })),
            gateway_logs: gatewayLogs.length,
            audit_logs: auditLogs.length
          },
          null,
          2
        )
      });
      setMessage("完整联调完成：主要后端模块已通过前端真实调用验证。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "联调失败，请检查 API 服务。");
      setIntegrationSteps((currentSteps) =>
        currentSteps.map((step) => (step.status === "running" ? { ...step, status: "failed", detail: "执行失败" } : step))
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveCurrentDraft() {
    if (!integrationState) {
      setMessage("还没有后端 Workflow，请先点击一键全链路联调创建资源。");
      return;
    }

    setBusy(true);
    setMessage("正在把当前画布同步到后端草稿...");

    try {
      await apiRequest<WorkflowResponse>(`/workflows/${integrationState.workflowId}/draft`, {
        method: "PUT",
        body: {
          actor_user_id: integrationState.userId,
          draft_definition: workflowDraft
        }
      });
      setMessage("草稿已保存到后端。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败，请检查 API 服务。");
    } finally {
      setBusy(false);
    }
  }

  async function saveWorkflow(actorUserId: string, agentId: string) {
    return apiRequest<WorkflowResponse>("/workflows", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        agent_id: agentId,
        name: "完整前后端联调工作流",
        description: "由可视化编辑器生成的 Start -> LLM -> End 工作流。",
        draft_definition: workflowDraft
      }
    });
  }

  async function publishWorkflow(actorUserId: string, workflowId: string) {
    return apiRequest<WorkflowVersionResponse>(`/workflows/${workflowId}/publish`, {
      method: "POST",
      body: {
        actor_user_id: actorUserId
      }
    });
  }

  return (
    <main className="min-h-screen bg-[#f6f7f9] text-[#172033] lg:grid lg:grid-cols-[320px_1fr_420px]">
      <aside className="border-b border-[#dfe4ee] bg-white p-4 lg:border-b-0 lg:border-r">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#2f6feb] text-white">
            <Workflow size={19} />
          </div>
          <div>
            <h1 className="text-base font-semibold">联调工作台</h1>
            <p className="text-xs text-[#667085]">覆盖运行时、网关与工作流主链路</p>
          </div>
        </div>

        <div className="mb-4 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-[#667085]">API 状态</span>
            <StatusPill status={apiStatus} />
          </div>
          <p className="text-xs leading-5 text-[#667085]">{API_BASE_URL}</p>
        </div>

        <section className="mb-5">
          <h2 className="mb-2 text-xs font-semibold uppercase text-[#667085]">节点组件</h2>
          <div className="space-y-2">
            {nodePalette.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.label}
                  className="flex w-full items-center gap-3 rounded-md border border-[#dfe4ee] bg-white px-3 py-2 text-left transition hover:border-[#2f6feb] hover:bg-[#f8fafc]"
                  onClick={() => addNode(item.label)}
                  type="button"
                >
                  <span className="grid h-8 w-8 place-items-center rounded border border-[#dfe4ee] text-[#2f6feb]">
                    <Icon size={16} />
                  </span>
                  <span>
                    <span className="block text-sm font-medium">{item.label}</span>
                    <span className="block text-xs text-[#667085]">{item.description}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="space-y-2">
          <button
            className="flex w-full items-center justify-center gap-2 rounded-md bg-[#2f6feb] px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[#255dc7] disabled:bg-[#9bb8f5]"
            disabled={busy || apiStatus !== "online"}
            onClick={runFullIntegration}
            type="button"
          >
            {busy ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
            一键全链路联调
          </button>
          <button
            className="flex w-full items-center justify-center gap-2 rounded-md border border-[#cfd7e6] bg-white px-3 py-2 text-sm font-medium transition hover:border-[#2f6feb] disabled:text-[#98a2b3]"
            disabled={busy}
            onClick={saveCurrentDraft}
            type="button"
          >
            <Save size={16} />
            保存当前草稿
          </button>
        </section>

        <div className="mt-5 rounded-lg border border-[#dfe4ee] bg-white p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Activity size={15} className="text-[#2f6feb]" />
            操作反馈
          </div>
          <p className="text-sm leading-6 text-[#667085]">{message}</p>
        </div>
      </aside>

      <section className="min-w-0">
        <div className="relative h-[520px] border-b border-[#dfe4ee] lg:h-[58vh]">
          <div className="absolute left-5 top-4 z-10 rounded-lg border border-[#dfe4ee] bg-white/95 px-4 py-3 shadow-sm backdrop-blur">
            <div className="text-sm font-semibold">工作流画布</div>
            <div className="mt-1 text-xs text-[#667085]">Start {"->"} LLM {"->"} End，支持拖拽、连线、保存、发布、运行</div>
          </div>
          <ReactFlow
            edges={edges}
            fitView
            nodes={nodes}
            onConnect={handleConnect}
            onEdgesChange={onEdgesChange}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onNodesChange={onNodesChange}
          >
            <Background color="#d9e0ec" gap={18} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>

        <section className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">全模块联调进度</h2>
              <p className="mt-1 text-xs text-[#667085]">按真实 API 顺序覆盖身份、Agent、Session、Skill、MCP、Memory、Context、Gateway 和 Workflow。</p>
            </div>
            <span className="rounded-full bg-[#eef4ff] px-2.5 py-1 text-xs font-medium text-[#2f6feb]">
              {integrationSteps.filter((step) => step.status === "success").length}/{integrationSteps.length}
            </span>
          </div>
          <div className="grid gap-2 xl:grid-cols-2">
            {integrationSteps.map((step) => (
              <IntegrationStepRow key={step.key} step={step} />
            ))}
          </div>
        </section>
      </section>

      <aside className="overflow-y-auto border-t border-[#dfe4ee] bg-white p-4 lg:border-l lg:border-t-0">
        <section className="mb-5">
          <div className="mb-3 flex items-center gap-2">
            <CircleDot size={17} className="text-[#2f6feb]" />
            <h2 className="text-sm font-semibold">节点属性</h2>
          </div>
          <div className="space-y-3 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
            <Field label="节点 ID" value={selectedNode?.id ?? "未选择"} />
            <Field label="节点类型" value={selectedNode?.data.label ? String(selectedNode.data.label) : "未选择"} />
          </div>
        </section>

        <section className="mb-5">
          <div className="mb-3 flex items-center gap-2">
            <Server size={17} className="text-[#2f6feb]" />
            <h2 className="text-sm font-semibold">后端资源</h2>
          </div>
          <div className="space-y-2 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
            <Field label="Owner" value={integrationState?.userId ?? "-"} compact />
            <Field label="Viewer" value={integrationState?.viewerId ?? "-"} compact />
            <Field label="Org" value={integrationState?.orgId ?? "-"} compact />
            <Field label="Team" value={integrationState?.teamId ?? "-"} compact />
            <Field label="Agent" value={integrationState?.agentId ?? "-"} compact />
            <Field label="Session" value={integrationState?.sessionId ?? "-"} compact />
            <Field label="Skill" value={integrationState?.skillId ?? "-"} compact />
            <Field label="MCP Tool" value={integrationState?.mcpToolId ?? "-"} compact />
            <Field label="Memory" value={integrationState?.memoryId ?? "-"} compact />
            <Field label="Workflow" value={integrationState?.workflowId ?? "-"} compact />
            <Field label="Run" value={integrationState?.runId ?? "-"} compact />
            <Field label="状态" value={integrationState?.runStatus ?? "-"} />
          </div>
        </section>

        <section className="mb-5 grid grid-cols-2 gap-2">
          <Metric label="Context" value={integrationState?.contextSectionCount ?? 0} />
          <Metric label="Node Runs" value={integrationState?.nodeRunCount ?? 0} />
          <Metric label="Gateway Logs" value={integrationState?.gatewayLogCount ?? 0} />
          <Metric label="Audit Logs" value={integrationState?.auditLogCount ?? 0} />
        </section>

        <section className="mb-5">
          <div className="mb-3 flex items-center gap-2">
            <GitBranch size={17} className="text-[#2f6feb]" />
            <h2 className="text-sm font-semibold">Workflow DSL</h2>
          </div>
          <pre className="max-h-[260px] overflow-auto rounded-lg border border-[#dfe4ee] bg-[#0f172a] p-3 text-xs leading-5 text-[#dbeafe]">
            {JSON.stringify(workflowDraft, null, 2)}
          </pre>
        </section>

        <section>
          <div className="mb-3 flex items-center gap-2">
            <FileText size={17} className="text-[#2f6feb]" />
            <h2 className="text-sm font-semibold">联调输出</h2>
          </div>
          <pre className="max-h-[320px] overflow-auto rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3 text-xs leading-5 text-[#344054]">
            {integrationState?.outputPreview ?? "完整联调完成后会显示上下文、Workflow 输出、节点日志、Gateway 日志和审计摘要。"}
          </pre>
        </section>
      </aside>
    </main>
  );
}

function StatusPill({ status }: { status: ApiStatus }) {
  const statusText = {
    checking: "检测中",
    online: "在线",
    offline: "离线"
  }[status];

  const statusClassName = {
    checking: "bg-[#fff7ed] text-[#c2410c]",
    online: "bg-[#ecfdf3] text-[#027a48]",
    offline: "bg-[#fef3f2] text-[#b42318]"
  }[status];

  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusClassName}`}>{statusText}</span>;
}

function IntegrationStepRow({ step }: { step: IntegrationStep }) {
  const statusIcon = {
    idle: <Clock3 size={15} />,
    running: <Loader2 className="animate-spin" size={15} />,
    success: <CheckCircle2 size={15} />,
    failed: <XCircle size={15} />
  }[step.status];

  const statusClassName = {
    idle: "border-[#dfe4ee] text-[#667085]",
    running: "border-[#bfdbfe] bg-[#eff6ff] text-[#1d4ed8]",
    success: "border-[#bbf7d0] bg-[#f0fdf4] text-[#047857]",
    failed: "border-[#fecaca] bg-[#fef2f2] text-[#b42318]"
  }[step.status];

  return (
    <article className={`rounded-lg border bg-white p-3 ${statusClassName}`}>
      <div className="mb-2 flex items-center gap-2">
        {statusIcon}
        <h3 className="text-sm font-semibold text-[#172033]">{step.title}</h3>
      </div>
      <p className="text-xs leading-5 text-[#667085]">{step.description}</p>
      <p className="mt-2 overflow-hidden text-ellipsis whitespace-nowrap text-xs font-medium">{step.detail}</p>
    </article>
  );
}

function Field({ label, value, compact = false }: { label: string; value: string; compact?: boolean }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-[#667085]">{label}</div>
      <div
        className={`overflow-hidden text-ellipsis rounded-md border border-[#dfe4ee] bg-white px-2 py-1.5 text-sm ${
          compact ? "font-mono text-[11px]" : ""
        }`}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
      <div className="text-xs font-medium text-[#667085]">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
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

async function apiRequestExpectError(path: string, options: { method?: string; body?: object }) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  return { status: response.status };
}

function formatApiErrorDetail(detail: ApiErrorPayload["detail"]): string | undefined {
  if (!detail) {
    return undefined;
  }

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg ?? JSON.stringify(item)).join("；");
  }

  return detail.msg ?? JSON.stringify(detail);
}
