"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useWorkspaceStore } from "@/stores/workspace";

export default function AgentContextSelect() {
  const workspace = useWorkspaceStore((state) => state.workspace);
  const agents = useWorkspaceStore((state) => state.agents);
  const selectedAgentId = useWorkspaceStore((state) => state.selectedAgentId);
  const setSelectedAgentId = useWorkspaceStore((state) => state.setSelectedAgentId);
  const refreshAgents = useWorkspaceStore((state) => state.refreshAgents);
  const busy = useWorkspaceStore((state) => state.busy);

  useEffect(() => {
    if (workspace) {
      void refreshAgents();
    }
  }, [workspace, refreshAgents]);

  if (agents.length === 0) {
    return (
      <Link
        className="inline-flex h-8 items-center justify-center rounded-lg border border-[#cfd7e6] bg-white px-3 text-xs font-medium text-[#2f6feb] transition hover:border-[#2f6feb]"
        href="/agents"
      >
        Create Agent
      </Link>
    );
  }

  return (
    <select
      aria-label="Agent context"
      className="h-8 min-w-[180px] rounded-lg border border-[#cfd7e6] bg-white px-2 text-xs text-[#172033] disabled:cursor-not-allowed disabled:opacity-50"
      disabled={busy}
      onChange={(event) => setSelectedAgentId(event.target.value)}
      value={selectedAgentId}
    >
      <option value="">Select an Agent</option>
      {agents.map((agent) => (
        <option key={agent.agent_id} value={agent.agent_id}>
          {agent.name}
        </option>
      ))}
    </select>
  );
}
