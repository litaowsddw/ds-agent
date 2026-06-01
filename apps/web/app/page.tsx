/** 首页 - 工作空间设置入口。

如果未创建工作空间，展示设置面板；已创建则跳转到工作流编辑器。
 */

"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Loader2, Network, Plus } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { showToast } from "@/components/layout/AppLayout";
import Panel from "@/components/ui/Panel";
import { TextInput } from "@/components/ui/Form";
import { PrimaryButton } from "@/components/ui/Button";

export default function HomePage() {
  const router = useRouter();
  const workspace = useWorkspaceStore((s) => s.workspace);
  const busy = useWorkspaceStore((s) => s.busy);
  const createWorkspace = useWorkspaceStore((s) => s.createWorkspace);

  // 已有工作空间，跳转到工作流编辑器
  useEffect(() => {
    if (workspace) {
      router.replace("/workflows");
    }
  }, [workspace, router]);

  if (workspace) return null;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8">
        <h2 className="text-2xl font-semibold text-[#172033]">欢迎使用 AgentFlow</h2>
        <p className="mt-2 text-sm text-[#667085]">
          创建一个工作空间后即可开始搭建 Agent 应用。MVP 阶段会自动创建一个本地用户、组织和团队。
        </p>
      </div>

      <SetupForm
        busy={busy}
        onSubmit={async (form) => {
          try {
            await createWorkspace(form);
            showToast("success", "工作空间已创建，可以开始创建 Agent。");
          } catch (error) {
            showToast("error", error instanceof Error ? error.message : "创建工作空间失败。");
          }
        }}
      />

      <div className="mt-8 grid grid-cols-3 gap-4">
        <WelcomeCard
          step={1}
          title="创建 Agent"
          description="定义 Agent 的名称和用途，配置 Workspace 指令。"
        />
        <WelcomeCard
          step={2}
          title="搭建 Workflow"
          description="拖拽节点、连线，配置 LLM/RAG/Tool 参数。"
        />
        <WelcomeCard
          step={3}
          title="发布运行"
          description="发布 Workflow 版本并同步执行，查看运行日志。"
        />
      </div>
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
    email: "owner@example.com",
    displayName: "Owner",
    orgName: "AgentFlow 工作空间",
    teamName: "默认团队",
  });

  return (
    <Panel title="创建工作空间" icon={<Network size={17} />}>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label="邮箱"
          value={form.email}
          onChange={(email) => setForm({ ...form, email })}
        />
        <TextInput
          label="显示名称"
          value={form.displayName}
          onChange={(displayName) => setForm({ ...form, displayName })}
        />
        <TextInput
          label="组织名称"
          value={form.orgName}
          onChange={(orgName) => setForm({ ...form, orgName })}
        />
        <TextInput
          label="团队名称"
          value={form.teamName}
          onChange={(teamName) => setForm({ ...form, teamName })}
        />
      </div>
      <PrimaryButton busy={busy} label="创建并进入 Studio" onClick={() => onSubmit(form)} />
    </Panel>
  );
}

function WelcomeCard({
  step,
  title,
  description,
}: {
  step: number;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-[#dfe4ee] bg-white p-4 shadow-sm">
      <div className="mb-3 grid h-7 w-7 place-items-center rounded-full bg-[#eef4ff] text-xs font-semibold text-[#2f6feb]">
        {step}
      </div>
      <h4 className="text-sm font-semibold text-[#172033]">{title}</h4>
      <p className="mt-1 text-xs leading-5 text-[#667085]">{description}</p>
    </div>
  );
}
