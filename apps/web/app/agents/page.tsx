/** Agent 管理页面。

创建 Agent、查看 Agent 列表、编辑 Workspace 文件。
 */

"use client";

import { useState, useEffect } from "react";
import { Bot, FileText, Loader2, Network, Save } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useRuntimeStore } from "@/stores/runtime";
import { showToast } from "@/components/layout/AppLayout";
import Panel from "@/components/ui/Panel";
import { TextInput, TextArea } from "@/components/ui/Form";
import { PrimaryButton } from "@/components/ui/Button";
import { Metric, EmptyText } from "@/components/ui/DataDisplay";

export default function AgentsPage() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const agents = useWorkspaceStore((s) => s.agents);
  const selectedAgentId = useWorkspaceStore((s) => s.selectedAgentId);
  const busy = useWorkspaceStore((s) => s.busy);
  const setSelectedAgentId = useWorkspaceStore((s) => s.setSelectedAgentId);
  const createAgent = useWorkspaceStore((s) => s.createAgent);
  const refreshAgents = useWorkspaceStore((s) => s.refreshAgents);
  const getSelectedAgent = useWorkspaceStore((s) => s.getSelectedAgent);

  const skills = useRuntimeStore((s) => s.skills);
  const mcpTools = useRuntimeStore((s) => s.mcpTools);
  const memories = useRuntimeStore((s) => s.memories);
  const sessions = useRuntimeStore((s) => s.sessions);

  const [agentForm, setAgentForm] = useState({
    name: "客服助手 Agent",
    description: "负责基于知识、工具和工作流回答用户问题。",
  });
  const [workspaceText, setWorkspaceText] = useState(
    "# AGENTS\n\n你是一个可靠的业务 Agent，回答时先给结论，再给依据。\n"
  );

  const selectedAgent = getSelectedAgent();

  useEffect(() => {
    if (workspace) {
      void refreshAgents();
    }
  }, [workspace, refreshAgents]);

  if (!workspace) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-[#667085]">
        请先在首页创建工作空间
      </div>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
      {/* 左栏：创建 Agent + Agent 列表 */}
      <div className="space-y-6">
        <Panel title="创建 Agent" icon={<Bot size={17} />}>
          <div className="space-y-3">
            <TextInput
              label="名称"
              value={agentForm.name}
              onChange={(name) => setAgentForm({ ...agentForm, name })}
            />
            <TextArea
              label="描述"
              rows={4}
              value={agentForm.description}
              onChange={(description) => setAgentForm({ ...agentForm, description })}
            />
            <PrimaryButton
              busy={busy}
              label="创建 Agent"
              onClick={async () => {
                try {
                  await createAgent(agentForm);
                  showToast("success", `Agent「${agentForm.name}」已创建。`);
                } catch (error) {
                  showToast("error", error instanceof Error ? error.message : "创建 Agent 失败。");
                }
              }}
            />
          </div>
        </Panel>

        <Panel title="Agent 列表" icon={<Network size={17} />}>
          <div className="space-y-2">
            {agents.length === 0 ? <EmptyText text="暂无 Agent。" /> : null}
            {agents.map((agent) => (
              <button
                key={agent.agent_id}
                className={`w-full rounded-lg border p-3 text-left text-sm transition ${
                  selectedAgentId === agent.agent_id
                    ? "border-[#2f6feb] bg-[#eef4ff]"
                    : "border-[#dfe4ee] bg-white hover:border-[#93c5fd]"
                }`}
                onClick={() => setSelectedAgentId(agent.agent_id)}
                type="button"
              >
                <div className="font-medium text-[#172033]">{agent.name}</div>
                <div className="mt-1 text-xs text-[#667085]">{agent.description}</div>
              </button>
            ))}
          </div>
        </Panel>
      </div>

      {/* 右栏：Agent Workspace */}
      <div className="space-y-6">
        <Panel title="Agent Workspace" icon={<FileText size={17} />}>
          <div className="mb-3 grid gap-2 sm:grid-cols-4">
            <Metric label="Skills" value={skills.length} />
            <Metric label="MCP Tools" value={mcpTools.length} />
            <Metric label="Memories" value={memories.length} />
            <Metric label="Sessions" value={sessions.length} />
          </div>
          <TextArea
            label="AGENTS.md"
            rows={12}
            value={workspaceText}
            onChange={setWorkspaceText}
          />
          <div className="mt-3 flex items-center justify-between text-xs text-[#667085]">
            <span>当前组织：{workspace.orgId.slice(0, 8)}</span>
            <button
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#2f6feb] px-3 py-2 text-sm font-medium text-white transition hover:bg-[#255dc7]"
              onClick={async () => {
                if (!selectedAgentId) {
                  showToast("error", "请先选择 Agent。");
                  return;
                }
                try {
                  const { apiRequest } = await import("@/lib/api");
                  await apiRequest(`/agents/${selectedAgentId}/workspace/file`, {
                    method: "PUT",
                    body: {
                      actor_user_id: workspace.userId,
                      file_kind: "AGENTS.md",
                      content: workspaceText,
                    },
                  });
                  showToast("success", "Agent Workspace 已保存。");
                } catch (error) {
                  showToast("error", error instanceof Error ? error.message : "保存失败。");
                }
              }}
              type="button"
            >
              <Save size={14} />
              保存 Workspace
            </button>
          </div>
        </Panel>
      </div>
    </div>
  );
}
