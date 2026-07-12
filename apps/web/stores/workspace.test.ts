import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Agent, WorkspaceState } from "@/types/agent";

const { apiRequestMock } = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiRequest: apiRequestMock };
});

import { useWorkspaceStore } from "@/stores/workspace";

describe("workspace agent refresh", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    useWorkspaceStore.setState({
      workspace: null,
      agents: [],
      selectedAgentId: "",
      busy: false,
    });
  });

  it("ignores an old agent response after switching workspaces", async () => {
    const oldWorkspace = workspace("org-1", "user-1");
    const currentWorkspace = workspace("org-2", "user-2");
    const currentAgent = agent("agent-2", "Current Agent", currentWorkspace.orgId);
    let resolveOldRequest!: (agents: Agent[]) => void;
    const oldRequest = new Promise<Agent[]>((resolve) => {
      resolveOldRequest = resolve;
    });
    apiRequestMock.mockReturnValueOnce(oldRequest);
    useWorkspaceStore.setState({ workspace: oldWorkspace });

    const refresh = useWorkspaceStore.getState().refreshAgents();
    useWorkspaceStore.setState({
      workspace: currentWorkspace,
      agents: [currentAgent],
      selectedAgentId: currentAgent.agent_id,
    });
    resolveOldRequest([agent("agent-1", "Old Agent", oldWorkspace.orgId)]);
    await refresh;

    expect(useWorkspaceStore.getState().agents).toEqual([currentAgent]);
    expect(useWorkspaceStore.getState().selectedAgentId).toBe(currentAgent.agent_id);
  });
});

function workspace(orgId: string, userId: string): WorkspaceState {
  return {
    orgId,
    userId,
    teamId: `team-${orgId}`,
    email: `${userId}@example.com`,
  };
}

function agent(agentId: string, name: string, orgId: string): Agent {
  return {
    agent_id: agentId,
    org_id: orgId,
    team_id: `team-${orgId}`,
    name,
    description: "",
    created_by: "user-1",
  };
}
