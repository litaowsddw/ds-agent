/** Studio home page. */

"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { Activity, Bot, Database, KeyRound, Network, PlugZap, Workflow } from "lucide-react";
import { useKnowledgeStore } from "@/stores/knowledge";
import { useRuntimeStore } from "@/stores/runtime";
import { useWorkflowStore } from "@/stores/workflow";
import { useWorkspaceStore } from "@/stores/workspace";
import { showToast } from "@/components/layout/AppLayout";
import Panel from "@/components/ui/Panel";
import { TextInput } from "@/components/ui/Form";
import { PrimaryButton } from "@/components/ui/Button";
import { Metric } from "@/components/ui/DataDisplay";

export default function HomePage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const busy = useWorkspaceStore((s) => s.busy);
  const agents = useWorkspaceStore((s) => s.agents);
  const createWorkspace = useWorkspaceStore((s) => s.createWorkspace);
  const refreshAgents = useWorkspaceStore((s) => s.refreshAgents);
  const knowledgeBases = useKnowledgeStore((s) => s.knowledgeBases);
  const modelProviders = useRuntimeStore((s) => s.modelProviders);
  const mcpTools = useRuntimeStore((s) => s.mcpTools);
  const workflows = useWorkflowStore((s) => s.workflows);
  const runs = useWorkflowStore((s) => s.runs);

  useEffect(() => {
    if (!workspace) return;
    void refreshAgents();
    void useKnowledgeStore.getState().refreshKbs(workspace.orgId, workspace.userId);
    void useRuntimeStore.getState().refreshRuntimeData(workspace.orgId, workspace.userId, undefined);
    void useWorkflowStore.getState().refreshWorkflows(workspace.orgId, workspace.userId);
    void useWorkflowStore.getState().refreshRuns(workspace.orgId, workspace.userId);
  }, [workspace, refreshAgents]);

  if (workspace) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div>
            <h2 className="text-2xl font-semibold text-[#172033]">AgentFlow Studio</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#667085]">
              当前工作空间已经就绪。按顺序配置模型、知识库、工具和 Agent，然后在 Workflow 画布发布运行。
            </p>
          </div>
          <Link
            className="inline-flex items-center justify-center rounded-lg bg-[#2f6feb] px-4 py-2 text-sm font-medium text-white hover:bg-[#255dc7]"
            href="/workflows"
          >
            打开 Workflow
          </Link>
        </div>

        <div className="grid gap-3 md:grid-cols-5">
          <Metric label="Agents" value={agents.length} />
          <Metric label="模型供应商" value={modelProviders.length} />
          <Metric label="知识库" value={knowledgeBases.length} />
          <Metric label="工具" value={mcpTools.length} />
          <Metric label="Runs" value={runs.length} />
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <StudioStep href="/models" icon={<KeyRound size={18} />} title="1. 配置模型" text="保存 DeepSeek、OpenAI 或其他 OpenAI-compatible 模型供应商。" done={modelProviders.length > 0} />
          <StudioStep href="/agents" icon={<Bot size={18} />} title="2. 创建 Agent" text="维护 Agent 描述、Workspace 指令和运行上下文。" done={agents.length > 0} />
          <StudioStep href="/knowledge" icon={<Database size={18} />} title="3. 构建知识库" text="上传文档、切片索引，并供 RAG 节点检索。" done={knowledgeBases.length > 0} />
          <StudioStep href="/tools" icon={<PlugZap size={18} />} title="4. 授权工具" text="注册 MCP Server 和 Tool，绑定给当前 Agent。" done={mcpTools.length > 0} />
          <StudioStep href="/workflows" icon={<Workflow size={18} />} title="5. 编排工作流" text="拖拽 LLM/RAG/Tool 节点，保存、发布并运行。" done={workflows.length > 0} />
          <StudioStep href="/runs" icon={<Activity size={18} />} title="6. 查看运行" text="检查 Run 输出、节点日志、缓存命中与失败原因。" done={runs.length > 0} />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-[#172033]">欢迎使用 AgentFlow</h2>
        <p className="mt-2 text-sm text-[#667085]">
          创建或恢复一个工作空间后即可进入 Studio。系统会自动创建本地用户、组织和团队，也会在邮箱已存在时恢复已有空间。
        </p>
      </div>

      <SetupForm
        busy={busy}
        onSubmit={async (form) => {
          try {
            await createWorkspace(form);
            showToast("success", "工作空间已就绪，可以开始配置模型、Agent 和 Workflow");
          } catch (error) {
            showToast("error", error instanceof Error ? error.message : "创建或恢复工作空间失败");
          }
        }}
      />
    </div>
  );
}

function SetupForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (form: { email: string; displayName: string; orgName: string; teamName: string }) => void;
}) {
  const [form, setForm] = React.useState({
    email: "",
    displayName: "",
    orgName: "",
    teamName: "",
  });

  return (
    <Panel title="创建或恢复工作空间" icon={<Network size={17} />}>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput label="邮箱" placeholder="name@company.com" value={form.email} onChange={(email) => setForm({ ...form, email })} />
        <TextInput label="显示名称" placeholder="你的名字" value={form.displayName} onChange={(displayName) => setForm({ ...form, displayName })} />
        <TextInput label="组织名称" placeholder="例如：研发中心" value={form.orgName} onChange={(orgName) => setForm({ ...form, orgName })} />
        <TextInput label="团队名称" placeholder="例如：默认团队" value={form.teamName} onChange={(teamName) => setForm({ ...form, teamName })} />
      </div>
      <PrimaryButton busy={busy} label="创建或恢复并进入 Studio" onClick={() => onSubmit(form)} />
    </Panel>
  );
}

function StudioStep({
  href,
  icon,
  title,
  text,
  done,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  text: string;
  done: boolean;
}) {
  return (
    <Link
      className="block rounded-xl border border-[#dfe4ee] bg-white p-4 shadow-sm transition hover:border-[#93c5fd] hover:shadow-md"
      href={href}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-[#eef4ff] text-[#2f6feb]">{icon}</span>
        <span className={`rounded-full px-2 py-1 text-xs ${done ? "bg-[#ecfdf3] text-[#027a48]" : "bg-[#fff7ed] text-[#c2410c]"}`}>
          {done ? "已配置" : "待配置"}
        </span>
      </div>
      <h3 className="text-sm font-semibold text-[#172033]">{title}</h3>
      <p className="mt-2 text-xs leading-5 text-[#667085]">{text}</p>
    </Link>
  );
}
