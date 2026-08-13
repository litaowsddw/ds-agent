"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot } from "lucide-react";
import { useWorkspaceStore } from "@/stores/workspace";
import { useWorkflowStore } from "@/stores/workflow";
import { useRuntimeStore } from "@/stores/runtime";
import ChatPanel from "@/components/chat/ChatPanel";
import EvolverPanel from "@/components/chat/EvolverPanel";
import WorkspaceRequired from "@/components/ui/WorkspaceRequired";

/** Chat 页面 - 与 Agent 对话 + Skill 自我进化 */
export default function ChatPage() {
  const { workspace, agents, selectedAgentId } = useWorkspaceStore();
  const workflows = useWorkflowStore((state) => state.workflows);
  const refreshWorkflows = useWorkflowStore((state) => state.refreshWorkflows);
  const refreshRuntimeData = useRuntimeStore((state) => state.refreshRuntimeData);
  const [activeTab, setActiveTab] = useState<"chat" | "evolver">("chat");

  useEffect(() => {
    if (!workspace || !selectedAgentId) return;
    void refreshWorkflows(workspace.orgId, workspace.userId, selectedAgentId);
    void refreshRuntimeData(workspace.orgId, workspace.userId, selectedAgentId);
  }, [workspace, selectedAgentId, refreshWorkflows, refreshRuntimeData]);

  if (!workspace) {
    return <WorkspaceRequired />;
  }

  const orgId = workspace.orgId;
  const actorUserId = workspace.userId;
  const agentId = selectedAgentId || "";
  const selectedAgent = agents?.find((agent) => agent.agent_id === agentId) || null;
  const validAgentId = selectedAgent?.agent_id || "";

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#f7f8fa]">
      <div className="border-b border-[#dfe4ee] bg-white px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <div className="text-sm font-semibold text-[#172033]">Agent 运行台</div>
            <div className="mt-1 text-xs text-[#667085]">
              {selectedAgent ? selectedAgent.name : "请选择 Agent"} · {workflows.length} 个 Workflow
            </div>
          </div>
        </div>
      </div>

      <div className="flex border-b border-[#dfe4ee] bg-white px-4">
        <button
          onClick={() => setActiveTab("chat")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "chat"
              ? "border-b-2 border-[#2f6feb] text-[#2f6feb]"
              : "text-[#667085] hover:text-[#172033]"
          }`}
        >
          对话
        </button>
        <button
          onClick={() => setActiveTab("evolver")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "evolver"
              ? "border-b-2 border-[#2f6feb] text-[#2f6feb]"
              : "text-[#667085] hover:text-[#172033]"
          }`}
        >
          Skill 进化
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {selectedAgent ? (
          activeTab === "chat" ? (
            <ChatPanel
              agentId={validAgentId}
              orgId={orgId}
              actorUserId={actorUserId}
              workflows={workflows}
              agent={selectedAgent}
            />
          ) : (
            <div className="p-4">
              <EvolverPanel agentId={validAgentId} orgId={orgId} />
            </div>
          )
        ) : (
          <div className="flex h-full items-center justify-center px-4">
            <div className="w-full max-w-md rounded-lg border border-[#dfe4ee] bg-white px-6 py-8 text-center shadow-sm">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-lg bg-[#eef4ff] text-[#2f6feb]">
                <Bot size={22} />
              </div>
              <h2 className="mt-4 text-base font-semibold text-[#172033]">请选择或创建 Agent</h2>
              <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-[#667085]">
                Chat 需要一个 Agent 作为运行主体。你可以在 Agents 页面创建 Agent，或从上方选择已有 Agent。
              </p>
              <Link
                className="mt-5 inline-flex h-9 items-center justify-center rounded-lg bg-[#2f6feb] px-4 text-sm font-medium text-white transition hover:bg-[#255dc7]"
                href="/agents"
              >
                前往 Agents
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
