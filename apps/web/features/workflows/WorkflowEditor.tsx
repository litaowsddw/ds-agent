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
  Database,
  GitBranch,
  Loader2,
  Play,
  Save,
  Server,
  ShieldCheck,
  Workflow
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type ApiStatus = "checking" | "online" | "offline";

type IntegrationState = {
  userId: string;
  orgId: string;
  agentId: string;
  workflowId: string;
  versionId: string;
  runId: string;
  runStatus: string;
  outputPreview: string;
};

type ApiErrorPayload = {
  detail?: string | { msg?: string } | Array<{ msg?: string }>;
};

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
  { label: "LLM", description: "模型推理", icon: Bot },
  { label: "RAG", description: "知识检索", icon: Database },
  { label: "Tool", description: "工具调用", icon: ShieldCheck }
];

export default function WorkflowEditor() {
  // nodes 保存画布中的节点状态，React Flow 会在拖拽、选中和移动时更新它。
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);

  // edges 保存节点之间的连线状态，用于生成后端 Workflow DSL。
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // selectedNodeId 保存右侧属性面板当前展示的节点 ID。
  const [selectedNodeId, setSelectedNodeId] = useState<string>("llm");

  // apiStatus 表示前端到 FastAPI 服务的健康检查结果。
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");

  // busy 表示当前是否有保存、发布或运行中的联调请求。
  const [busy, setBusy] = useState(false);

  // message 保存页面顶部的短反馈，避免用户不知道当前动作是否完成。
  const [message, setMessage] = useState("准备就绪，点击一键联调即可创建测试链路。");

  // integrationState 保存后端真实返回的用户、组织、Agent、Workflow 和运行结果。
  const [integrationState, setIntegrationState] = useState<IntegrationState | null>(null);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId);

  const workflowDraft = useMemo(() => {
    return {
      version: "1.0",
      nodes: nodes.map((node) => {
        // label 是用户在画布中看到的节点名称，转换为小写后作为后端节点类型。
        const label = String(node.data.label);

        return {
          id: node.id,
          type: label.toLowerCase(),
          config: {
            label,
            provider: label === "LLM" ? "mock" : undefined,
            model: label === "LLM" ? "mock-model" : undefined,
            prompt: label === "LLM" ? "请总结输入并给出下一步建议" : undefined
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
    // nodeIndex 用于生成稳定且不重复的节点 ID。
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

  async function runFullIntegration() {
    setBusy(true);
    setMessage("正在创建测试用户、组织和 Agent...");

    try {
      const timestamp = Date.now();

      // user 保存本轮联调的测试用户，后端 MVP 阶段使用显式 actor_user_id。
      const user = await apiRequest<{ user_id: string }>("/identity/users/register", {
        method: "POST",
        body: {
          email: `designer-${timestamp}@example.com`,
          display_name: "工作流设计师",
          password: "password123"
        }
      });

      // organization 保存测试组织，后续 Agent 和 Workflow 都会绑定到该组织。
      const organization = await apiRequest<{ org_id: string }>("/identity/organizations", {
        method: "POST",
        body: {
          creator_user_id: user.user_id,
          name: "AgentFlow 联调组织"
        }
      });

      // agent 保存后端真实创建的 Agent，用于验证组织隔离和 Workflow 绑定关系。
      const agent = await apiRequest<{ agent_id: string }>("/agents", {
        method: "POST",
        body: {
          actor_user_id: user.user_id,
          org_id: organization.org_id,
          name: "可视化工作流 Agent",
          description: "由前端联调页面创建，用于验证端到端链路。"
        }
      });

      setMessage("正在保存画布草稿并发布 Workflow 版本...");

      const workflow = await saveWorkflow(user.user_id, agent.agent_id);
      const version = await publishWorkflow(user.user_id, workflow.workflow_id);

      setMessage("正在执行发布版本并拉取运行结果...");

      const run = await apiRequest<WorkflowRunResponse>("/workflow-runs", {
        method: "POST",
        body: {
          actor_user_id: user.user_id,
          version_id: version.version_id,
          input_data: {
            text: "请验证前后端联调链路，并输出一段简洁总结。"
          },
          async_mode: false
        }
      });

      const outputPreview = JSON.stringify(run.output_data, null, 2);

      setIntegrationState({
        userId: user.user_id,
        orgId: organization.org_id,
        agentId: agent.agent_id,
        workflowId: workflow.workflow_id,
        versionId: version.version_id,
        runId: run.run_id,
        runStatus: run.status,
        outputPreview
      });
      setMessage("联调完成：工作流已保存、发布并成功运行。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "联调失败，请检查 API 服务。");
    } finally {
      setBusy(false);
    }
  }

  async function saveCurrentDraft() {
    if (!integrationState) {
      setMessage("还没有后端 Workflow，请先点击一键联调创建链路。");
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
        name: "前后端联调工作流",
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
    <main className="min-h-screen bg-[#f6f7f9] text-[#172033] lg:grid lg:grid-cols-[300px_1fr_380px]">
      <aside className="border-b border-[#dfe4ee] bg-white p-4 lg:border-b-0 lg:border-r">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg bg-[#2f6feb] text-white">
            <Workflow size={19} />
          </div>
          <div>
            <h1 className="text-base font-semibold">工作流工作台</h1>
            <p className="text-xs text-[#667085]">可视化搭建与端到端联调</p>
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
          <h2 className="mb-2 text-xs font-semibold uppercase text-[#667085]">节点</h2>
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
            一键联调运行
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

      <section className="relative h-[560px] lg:h-screen">
        <div className="absolute left-5 top-4 z-10 rounded-lg border border-[#dfe4ee] bg-white/95 px-4 py-3 shadow-sm backdrop-blur">
          <div className="text-sm font-semibold">前后端联调工作流</div>
          <div className="mt-1 text-xs text-[#667085]">Start {"->"} LLM {"->"} End，可拖拽、连线、发布、运行</div>
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
            <h2 className="text-sm font-semibold">后端联调结果</h2>
          </div>
          <div className="space-y-2 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3">
            <Field label="User" value={integrationState?.userId ?? "-"} compact />
            <Field label="Org" value={integrationState?.orgId ?? "-"} compact />
            <Field label="Agent" value={integrationState?.agentId ?? "-"} compact />
            <Field label="Workflow" value={integrationState?.workflowId ?? "-"} compact />
            <Field label="Version" value={integrationState?.versionId ?? "-"} compact />
            <Field label="Run" value={integrationState?.runId ?? "-"} compact />
            <Field label="状态" value={integrationState?.runStatus ?? "-"} />
          </div>
        </section>

        <section className="mb-5">
          <div className="mb-3 flex items-center gap-2">
            <GitBranch size={17} className="text-[#2f6feb]" />
            <h2 className="text-sm font-semibold">Workflow DSL</h2>
          </div>
          <pre className="max-h-[300px] overflow-auto rounded-lg border border-[#dfe4ee] bg-[#0f172a] p-3 text-xs leading-5 text-[#dbeafe]">
            {JSON.stringify(workflowDraft, null, 2)}
          </pre>
        </section>

        <section>
          <div className="mb-3 flex items-center gap-2">
            <CheckCircle2 size={17} className="text-[#2f6feb]" />
            <h2 className="text-sm font-semibold">运行输出</h2>
          </div>
          <pre className="max-h-[260px] overflow-auto rounded-lg border border-[#dfe4ee] bg-[#f8fafc] p-3 text-xs leading-5 text-[#344054]">
            {integrationState?.outputPreview ?? "运行完成后会显示后端返回的节点输出。"}
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
