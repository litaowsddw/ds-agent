import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RunsPage from "@/app/runs/page";
import { useWorkflowStore } from "@/stores/workflow";
import { useWorkspaceStore } from "@/stores/workspace";

describe("RunsPage workflow hydration", () => {
  const refreshRuns = vi.fn().mockResolvedValue(undefined);
  const refreshWorkflows = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    refreshRuns.mockClear();
    refreshWorkflows.mockClear();
    useWorkspaceStore.setState({
      workspace: { orgId: "org-a", userId: "user-a", teamId: "team-a", email: "a@example.com" },
      agents: [{
        agent_id: "agent-a",
        org_id: "org-a",
        team_id: "team-a",
        name: "客服 Agent",
        description: "",
        created_by: "user-a",
      }],
      selectedAgentId: "agent-a",
      busy: false,
    });
    useWorkflowStore.setState({
      workflows: [],
      runs: [],
      versions: [],
      nodeRuns: [],
      selectedRunId: "",
      refreshRuns,
      refreshWorkflows,
    });
  });

  it("hydrates the current Agent workflows on direct navigation", async () => {
    render(<RunsPage />);

    await waitFor(() => {
      expect(refreshWorkflows).toHaveBeenCalledWith("org-a", "user-a", "agent-a");
    });
  });
});
