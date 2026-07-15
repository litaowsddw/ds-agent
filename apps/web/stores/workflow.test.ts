import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));

vi.mock("@/lib/api", () => ({ apiRequest: apiRequestMock }));

import { useWorkflowStore } from "@/stores/workflow";

describe("workflow run requests", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    useWorkflowStore.setState({
      workflows: [
        {
          workflow_id: "workflow-1",
          agent_id: "agent-1",
          name: "Workflow",
          description: "",
          draft_definition: { version: "1", nodes: [], edges: [] },
          published_version_id: "version-1",
        },
      ],
      selectedWorkflowId: "workflow-1",
      runs: [],
      nodeRuns: [],
      selectedRunId: "",
    });
  });

  it("does not send legacy actor_user_id to the strict workflow run schema", async () => {
    apiRequestMock
      .mockResolvedValueOnce({
        run_id: "run-1",
        workflow_id: "workflow-1",
        version_id: "version-1",
        agent_id: "agent-1",
        status: "succeeded",
        output_data: {},
        error_message: "",
        created_at: "2026-07-15T00:00:00Z",
        updated_at: null,
      })
      .mockResolvedValueOnce([]);

    await useWorkflowStore.getState().runWorkflow("user-1", "hello");

    expect(apiRequestMock).toHaveBeenNthCalledWith(1, "/workflow-runs", {
      method: "POST",
      body: {
        version_id: "version-1",
        input_data: { text: "hello" },
        async_mode: false,
      },
    });
  });

  it("removes only the explicitly selected connection", () => {
    useWorkflowStore.setState({
      edges: [
        { id: "start-llm", source: "start", target: "llm" },
        { id: "llm-end", source: "llm", target: "end" },
      ],
      selectedEdgeId: "start-llm",
    });

    useWorkflowStore.getState().removeSelectedEdge();

    expect(useWorkflowStore.getState().edges).toEqual([
      { id: "llm-end", source: "llm", target: "end" },
    ]);
    expect(useWorkflowStore.getState().selectedEdgeId).toBe("");
  });
});
