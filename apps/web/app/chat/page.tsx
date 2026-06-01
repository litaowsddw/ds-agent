"use client";

import { useState } from "react";
import { useWorkspaceStore } from "@/stores/workspace";
import ChatPanel from "@/components/chat/ChatPanel";
import EvolverPanel from "@/components/chat/EvolverPanel";

/** Chat 页面 - 与 Agent 对话 + Skill 自我进化 */
export default function ChatPage() {
  const { workspace, agents, selectedAgentId, setSelectedAgentId } = useWorkspaceStore();
  const [activeTab, setActiveTab] = useState<"chat" | "evolver">("chat");

  const orgId = workspace?.orgId || "";
  const agentId = selectedAgentId || "";

  return (
    <div className="flex h-full">
      {/* 左侧：Agent 列表 */}
      <div className="w-64 border-r border-gray-200 dark:border-gray-700 flex flex-col">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-sm font-medium text-gray-900 dark:text-gray-100">Agents</h2>
        </div>
        <div className="flex-1 overflow-y-auto">
          {agents?.map((agent) => (
            <button
              key={agent.agent_id}
              onClick={() => setSelectedAgentId(agent.agent_id)}
              className={`w-full text-left px-4 py-2.5 text-sm border-b border-gray-100
                dark:border-gray-800 transition-colors
                ${agent.agent_id === agentId
                  ? "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                }`}
            >
              <div className="font-medium">{agent.name}</div>
              <div className="text-xs text-gray-400 truncate">{agent.description}</div>
            </button>
          ))}
        </div>
      </div>

      {/* 右侧：Chat/Evolver */}
      <div className="flex-1 flex flex-col">
        {/* Tab 切换 */}
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setActiveTab("chat")}
            className={`px-4 py-2 text-sm font-medium transition-colors
              ${activeTab === "chat"
                ? "text-blue-600 border-b-2 border-blue-600 dark:text-blue-400 dark:border-blue-400"
                : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              }`}
          >
            Chat
          </button>
          <button
            onClick={() => setActiveTab("evolver")}
            className={`px-4 py-2 text-sm font-medium transition-colors
              ${activeTab === "evolver"
                ? "text-blue-600 border-b-2 border-blue-600 dark:text-blue-400 dark:border-blue-400"
                : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
              }`}
          >
            Skill Evolver
          </button>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-hidden">
          {agentId ? (
            activeTab === "chat" ? (
              <ChatPanel agentId={agentId} orgId={orgId} />
            ) : (
              <div className="p-4">
                <EvolverPanel agentId={agentId} orgId={orgId} />
              </div>
            )
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              <p className="text-sm">Select an Agent to start</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
