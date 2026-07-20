import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));

vi.mock("@/lib/api", () => ({ apiRequest: apiRequestMock }));

import { useWorkflowStore } from "@/stores/workflow";
import { WORKFLOW_TEMPLATES } from "@/components/workflows/workflowTemplates";

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

  it("keeps named condition branches when adding and serializing canvas connections", () => {
    useWorkflowStore.setState({
      nodes: ["start", "check", "end"].map((id) => ({
        id,
        type: id === "check" ? "condition" : id,
        position: { x: 0, y: 0 },
        data: {
          label: id,
          config: id === "check"
            ? { left: "{{input.status}}", operator: "equals", value: "approved", value_type: "string" }
            : {},
        },
      })) as never,
      edges: [{ id: "start-check", source: "start", target: "check" }],
    });

    expect(useWorkflowStore.getState().connectNodes("check", "end", "true")).toMatchObject({ valid: true });
    expect(useWorkflowStore.getState().connectNodes("check", "end", "false")).toMatchObject({ valid: true });
    expect(useWorkflowStore.getState().connectNodes("check", "end", "true")).toEqual({
      valid: false,
      message: "The true branch is already connected",
    });

    expect(useWorkflowStore.getState().getWorkflowDraft().edges).toEqual([
      { source: "start", target: "check" },
      { source: "check", target: "end", branch: "true" },
      { source: "check", target: "end", branch: "false" },
    ]);
    expect(useWorkflowStore.getState().getWorkflowDraft().nodes[1].config).toEqual({
      left: "{{input.status}}",
      operator: "equals",
      value: "approved",
    });
  });

  it("serializes optional run protection as steps and LLM-call guards, including zero calls", () => {
    useWorkflowStore.setState({ executionLimits: { max_steps: "12", max_llm_calls: "0" } });

    expect(useWorkflowStore.getState().getWorkflowDraft().execution_limits).toEqual({
      max_steps: 12,
      max_llm_calls: 0,
    });

    useWorkflowStore.getState().setExecutionLimits({ max_steps: "", max_llm_calls: "" });
    expect(useWorkflowStore.getState().getWorkflowDraft()).not.toHaveProperty("execution_limits");
  });

  it("loads and template-copies run protection without treating it as a billing policy", () => {
    const template = WORKFLOW_TEMPLATES.find((item) => item.id === "content-polish");
    if (!template) throw new Error("content template is missing");
    const guardedTemplate = {
      ...template,
      definition: {
        ...template.definition,
        execution_limits: { max_steps: 30, max_llm_calls: 2 },
      },
    };

    useWorkflowStore.getState().applyWorkflowTemplate(guardedTemplate);
    expect(useWorkflowStore.getState().executionLimits).toEqual({ max_steps: "30", max_llm_calls: "2" });

    useWorkflowStore.setState({
      workflows: [{
        workflow_id: "guarded-workflow",
        agent_id: "agent-1",
        name: "Guarded",
        description: "",
        draft_definition: {
          version: "1.0",
          nodes: [],
          edges: [],
          execution_limits: { max_steps: 8, max_llm_calls: 0 },
        },
        published_version_id: null,
      }],
    });
    useWorkflowStore.getState().setSelectedWorkflowId("guarded-workflow");
    expect(useWorkflowStore.getState().executionLimits).toEqual({ max_steps: "8", max_llm_calls: "0" });
  });

  it("blocks invalid run protection before an unsafe draft can be sent", () => {
    useWorkflowStore.setState({ executionLimits: { max_steps: "501", max_llm_calls: "-1" } });

    expect(() => useWorkflowStore.getState().getWorkflowDraft()).toThrow("max_steps must be between 1 and 500");
  });

  it("loads a template as a new isolated draft instead of overwriting the selected workflow", () => {
    const template = WORKFLOW_TEMPLATES.find((item) => item.id === "knowledge-answer");
    if (!template) throw new Error("knowledge template is missing");

    useWorkflowStore.setState({
      selectedWorkflowId: "workflow-1",
      selectedRunId: "run-old",
      nodeRuns: [{ node_run_id: "node-old" } as never],
      workflowForm: { name: "Existing workflow", description: "Existing", input: "keep this input" },
    });

    useWorkflowStore.getState().applyWorkflowTemplate(template);

    const state = useWorkflowStore.getState();
    expect(state.selectedWorkflowId).toBe("");
    expect(state.selectedRunId).toBe("");
    expect(state.nodeRuns).toEqual([]);
    expect(state.workflowForm).toEqual({
      name: "知识库问答",
      description: template.description,
      input: "keep this input",
    });
    expect(state.nodes.map((node) => node.id)).toEqual([
      "start",
      "retrieve_knowledge",
      "grounded_answer",
      "end",
    ]);
    expect(state.edges.map((edge) => [edge.source, edge.target])).toEqual([
      ["start", "retrieve_knowledge"],
      ["retrieve_knowledge", "grounded_answer"],
      ["grounded_answer", "end"],
    ]);

    state.updateSelectedNodeConfig({ kb_id: "kb-new" });
    expect(template.definition.nodes.find((node) => node.id === "retrieve_knowledge")?.config.kb_id).toBe("");
  });
});
