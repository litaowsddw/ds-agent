import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RunsPage from "@/app/runs/page";
import { useWorkflowStore } from "@/stores/workflow";
import { useWorkspaceStore } from "@/stores/workspace";

describe("RunsPage workflow hydration", () => {
  const refreshRuns = vi.fn().mockResolvedValue(undefined);
  const refreshWorkflows = vi.fn().mockResolvedValue(undefined);
  const loadNodeRuns = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    refreshRuns.mockClear();
    refreshWorkflows.mockClear();
    loadNodeRuns.mockClear();
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
      loadNodeRuns,
    });
  });

  it("hydrates the current Agent workflows on direct navigation", async () => {
    render(<RunsPage />);

    await waitFor(() => {
      expect(refreshWorkflows).toHaveBeenCalledWith("org-a", "user-a", "agent-a");
    });
  });

  it("loads the selected run and refreshes active executions", async () => {
    vi.useFakeTimers();
    try {
      useWorkflowStore.setState({
        runs: [{
          run_id: "run-active",
          workflow_id: "workflow-a",
          version_id: "version-a",
          agent_id: "agent-a",
          input_data: { text: "hello" },
          status: "running",
          output_data: {},
          error_message: "",
          created_at: "2026-07-20T00:00:00Z",
          started_at: "2026-07-20T00:00:01Z",
          finished_at: null,
          updated_at: "2026-07-20T00:00:01Z",
        }],
        selectedRunId: "run-active",
      });

      render(<RunsPage />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });

      expect(screen.getByText("运行仍在进行中，节点详情每 3 秒自动刷新。")).toBeInTheDocument();
      expect(loadNodeRuns).toHaveBeenCalledWith("run-active", "user-a");
      expect(refreshRuns).toHaveBeenCalledWith("org-a", "user-a");
    } finally {
      vi.useRealTimers();
    }
  });
});
