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

  it("checks the current canvas through the workflow preflight endpoint", async () => {
    apiRequestMock.mockResolvedValueOnce({ valid: false, errors: ["End 节点无法从 Start 节点到达"] });

    const result = await useWorkflowStore.getState().validateWorkflow("user-1");

    expect(apiRequestMock).toHaveBeenCalledWith("/workflows/workflow-1/validate", {
      method: "POST",
      body: expect.objectContaining({
        actor_user_id: "user-1",
        draft_definition: expect.any(Object),
      }),
    });
    expect(result).toEqual({ valid: false, errors: ["End 节点无法从 Start 节点到达"] });
    expect(useWorkflowStore.getState().validation).toEqual(result);
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

  it("adds an explicit connection only when it is safe for the execution graph", () => {
    useWorkflowStore.setState({
      nodes: ["start", "llm", "rag", "end"].map((id) => ({
        id,
        type: id,
        position: { x: 0, y: 0 },
        data: { label: id },
      })) as never,
      edges: [
        { id: "start-llm", source: "start", target: "llm" },
        { id: "llm-end", source: "llm", target: "end" },
      ],
    });

    expect(useWorkflowStore.getState().connectNodes("llm", "rag")).toEqual({
      valid: true,
      message: "Connection is valid",
    });
    expect(useWorkflowStore.getState().edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: "llm", target: "rag" }),
    ]));

    expect(useWorkflowStore.getState().connectNodes("llm", "rag")).toEqual({
      valid: false,
      message: "This connection already exists",
    });
    expect(useWorkflowStore.getState().connectNodes("end", "start")).toEqual({
      valid: false,
      message: "End cannot have an outgoing connection",
    });
  });

  it("blocks a cycle before the user saves or publishes the workflow", () => {
    useWorkflowStore.setState({
      nodes: ["first", "second", "third"].map((id) => ({
        id,
        type: "llm",
        position: { x: 0, y: 0 },
        data: { label: id },
      })) as never,
      edges: [
        { id: "first-second", source: "first", target: "second" },
        { id: "second-third", source: "second", target: "third" },
      ],
    });

    expect(useWorkflowStore.getState().validateConnection("third", "first")).toEqual({
      valid: false,
      message: "This connection would create a cycle",
    });
  });
});
