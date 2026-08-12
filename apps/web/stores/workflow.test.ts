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

describe("canvas editor", () => {
  function seedCanvas() {
    useWorkflowStore.setState({
      nodes: [
        { id: "start", type: "start", position: { x: 80, y: 260 }, data: { label: "Start", config: {} } },
        { id: "llm", type: "llm", position: { x: 380, y: 260 }, data: { label: "LLM", config: { provider: "p", model: "m" } } },
        { id: "end", type: "end", position: { x: 680, y: 260 }, data: { label: "End", config: {} } },
      ] as never,
      edges: [
        { id: "start-llm", source: "start", target: "llm", animated: true },
        { id: "llm-end", source: "llm", target: "end", animated: true },
      ],
      selectedNodeId: "",
      selectedEdgeId: "",
      history: { past: [], future: [] },
      pendingAddPosition: null,
      validation: null,
    });
  }

  const paletteLlm = { type: "rag", label: "Knowledge Retrieval", description: "", group: "Knowledge" as const, icon: "", capability: "executable" as const };

  beforeEach(() => {
    seedCanvas();
  });

  it("persists canvas positions in the workflow draft and hydrates them back", () => {
    const draft = useWorkflowStore.getState().getWorkflowDraft();
    expect(draft.nodes.map((node) => node.position)).toEqual([
      { x: 80, y: 260 },
      { x: 380, y: 260 },
      { x: 680, y: 260 },
    ]);

    useWorkflowStore.setState({
      workflows: [{
        workflow_id: "positioned",
        agent_id: "agent-1",
        name: "Positioned",
        description: "",
        draft_definition: {
          version: "1.0",
          nodes: [
            { id: "start", type: "start", config: {}, position: { x: 10, y: 20 } },
            { id: "llm", type: "llm", config: { provider: "p", model: "m" } },
            { id: "end", type: "end", config: {}, position: { x: 900, y: 40 } },
          ],
          edges: [
            { source: "start", target: "llm" },
            { source: "llm", target: "end" },
          ],
        },
        published_version_id: null,
      }],
    });
    useWorkflowStore.getState().setSelectedWorkflowId("positioned");
    const positions = Object.fromEntries(
      useWorkflowStore.getState().nodes.map((node) => [node.id, node.position])
    );
    expect(positions.start).toEqual({ x: 10, y: 20 });
    expect(positions.end).toEqual({ x: 900, y: 40 });
    // Nodes without saved coordinates fall back to a deterministic layout.
    expect(positions.llm.y).toBe(260);
  });

  it("places palette-added nodes at the canvas pointer position", () => {
    useWorkflowStore.setState({ pendingAddPosition: { x: 500, y: 320 } });
    useWorkflowStore.getState().addNode(paletteLlm);
    const added = useWorkflowStore.getState().nodes.find((node) => node.type === "rag");
    expect(added?.position).toEqual({ x: 500, y: 320 });
    expect(useWorkflowStore.getState().selectedNodeId).toBe(added?.id);
  });

  it("connects a quick-added node to its source in one undoable step", () => {
    const result = useWorkflowStore.getState().connectNewNode("llm", undefined, paletteLlm, { x: 520, y: 120 });
    expect(result.valid).toBe(true);
    const state = useWorkflowStore.getState();
    const added = state.nodes.find((node) => node.type === "rag");
    expect(added).toBeDefined();
    expect(state.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: "llm", target: added?.id }),
    ]));
    expect(state.history.past).toHaveLength(1);

    state.undo();
    expect(useWorkflowStore.getState().nodes.find((node) => node.type === "rag")).toBeUndefined();
    state.redo();
    expect(useWorkflowStore.getState().nodes.find((node) => node.type === "rag")).toBeDefined();
  });

  it("rejects a quick-add when the source branch is already occupied", () => {
    useWorkflowStore.setState({
      nodes: [
        { id: "start", type: "start", position: { x: 0, y: 0 }, data: { label: "Start", config: {} } },
        { id: "check", type: "condition", position: { x: 200, y: 0 }, data: { label: "Condition", config: { left: "{{input.text}}", operator: "exists" } } },
        { id: "end", type: "end", position: { x: 400, y: 0 }, data: { label: "End", config: {} } },
      ] as never,
      edges: [
        { id: "start-check", source: "start", target: "check" },
        { id: "check-end-true", source: "check", target: "end", sourceHandle: "true" },
      ],
    });

    const result = useWorkflowStore.getState().connectNewNode("check", "true", paletteLlm, { x: 0, y: 0 });
    expect(result).toEqual({ valid: false, message: "The true branch is already connected" });
    expect(useWorkflowStore.getState().nodes.filter((node) => node.type === "rag")).toHaveLength(0);
  });

  it("duplicates selected nodes except start and end, with new ids and offsets", () => {
    useWorkflowStore.setState({ selectedNodeId: "llm" });
    const count = useWorkflowStore.getState().duplicateSelectedNodes();
    expect(count).toBe(1);
    const state = useWorkflowStore.getState();
    const copy = state.nodes.find((node) => node.type === "llm" && node.id !== "llm");
    expect(copy?.position).toEqual({ x: 428, y: 308 });
    expect(copy?.id).not.toBe("llm");
    expect(state.nodes.filter((node) => node.type === "start")).toHaveLength(1);

    useWorkflowStore.setState({ selectedNodeId: "start" });
    expect(useWorkflowStore.getState().duplicateSelectedNodes()).toBe(0);
  });

  it("deletes the current selection while protecting start and end", () => {
    useWorkflowStore.setState({ selectedNodeId: "llm", selectedEdgeId: "" });
    useWorkflowStore.getState().deleteSelection();
    let state = useWorkflowStore.getState();
    expect(state.nodes.map((node) => node.id)).toEqual(["start", "end"]);
    expect(state.edges).toEqual([]);

    useWorkflowStore.setState({ selectedNodeId: "start" });
    useWorkflowStore.getState().deleteSelection();
    state = useWorkflowStore.getState();
    expect(state.nodes.map((node) => node.id)).toEqual(["start", "end"]);
  });

  it("restores the previous canvas on undo and clears redo history on the next edit", () => {
    useWorkflowStore.getState().addNodeAt(paletteLlm, { x: 100, y: 100 });
    expect(useWorkflowStore.getState().history.past).toHaveLength(1);

    useWorkflowStore.getState().undo();
    expect(useWorkflowStore.getState().nodes.map((node) => node.id)).toEqual(["start", "llm", "end"]);
    expect(useWorkflowStore.getState().history.future).toHaveLength(1);

    useWorkflowStore.getState().redo();
    expect(useWorkflowStore.getState().nodes.some((node) => node.type === "rag")).toBe(true);

    useWorkflowStore.getState().undo();
    useWorkflowStore.getState().addNodeAt(paletteLlm, { x: 200, y: 200 });
    expect(useWorkflowStore.getState().history.future).toEqual([]);
  });

  it("lays out nodes in topological layers from the start node", () => {
    useWorkflowStore.setState({
      nodes: [
        { id: "end", type: "end", position: { x: 0, y: 0 }, data: { label: "End", config: {} } },
        { id: "llm", type: "llm", position: { x: 0, y: 0 }, data: { label: "LLM", config: {} } },
        { id: "start", type: "start", position: { x: 0, y: 0 }, data: { label: "Start", config: {} } },
        { id: "check", type: "condition", position: { x: 0, y: 0 }, data: { label: "Condition", config: {} } },
      ] as never,
      edges: [
        { id: "1", source: "start", target: "llm" },
        { id: "2", source: "llm", target: "check" },
        { id: "3", source: "check", target: "end", sourceHandle: "true" },
      ],
    });

    useWorkflowStore.getState().applyAutoLayout();
    const positions = Object.fromEntries(
      useWorkflowStore.getState().nodes.map((node) => [node.id, node.position])
    );
    expect(positions.start.x).toBeLessThan(positions.llm.x);
    expect(positions.llm.x).toBeLessThan(positions.check.x);
    expect(positions.check.x).toBeLessThan(positions.end.x);
  });

  it("splits an edge when inserting a node into it, in one undo step", () => {
    const ok = useWorkflowStore.getState().insertNodeIntoEdge("llm-end", paletteLlm, { x: 520, y: 260 });
    expect(ok).toBe(true);
    const state = useWorkflowStore.getState();
    const added = state.nodes.find((node) => node.type === "rag");
    expect(added?.position).toEqual({ x: 520, y: 260 });
    expect(state.edges.some((edge) => edge.source === "llm" && edge.target === added?.id)).toBe(true);
    expect(state.edges.some((edge) => edge.source === added?.id && edge.target === "end")).toBe(true);
    expect(state.edges.some((edge) => edge.id === "llm-end")).toBe(false);
    expect(state.history.past).toHaveLength(1);

    state.undo();
    expect(useWorkflowStore.getState().edges.map((edge) => edge.id)).toContain("llm-end");
  });

  it("keeps the condition branch on the upstream half when inserting into a branch edge", () => {
    useWorkflowStore.setState({
      nodes: [
        { id: "start", type: "start", position: { x: 0, y: 0 }, data: { label: "Start", config: {} } },
        { id: "check", type: "condition", position: { x: 200, y: 0 }, data: { label: "Condition", config: {} } },
        { id: "end", type: "end", position: { x: 400, y: 0 }, data: { label: "End", config: {} } },
      ] as never,
      edges: [
        { id: "start-check", source: "start", target: "check" },
        { id: "check-end-true", source: "check", target: "end", sourceHandle: "true" },
      ],
    });

    useWorkflowStore.getState().insertNodeIntoEdge("check-end-true", paletteLlm, { x: 300, y: 0 });
    const state = useWorkflowStore.getState();
    const added = state.nodes.find((node) => node.type === "rag");
    const upstream = state.edges.find((edge) => edge.source === "check" && edge.target === added?.id);
    const downstream = state.edges.find((edge) => edge.source === added?.id && edge.target === "end");
    expect(upstream?.sourceHandle).toBe("true");
    expect(downstream?.sourceHandle).toBeUndefined();
  });

  it("renames a node through saved display metadata", () => {
    useWorkflowStore.getState().renameNode("llm", "起草答复");
    expect(
      useWorkflowStore.getState().nodes.find((node) => node.id === "llm")?.data.config?.display_name
    ).toBe("起草答复");

    useWorkflowStore.getState().undo();
    expect(
      useWorkflowStore.getState().nodes.find((node) => node.id === "llm")?.data.config?.display_name
    ).toBeUndefined();
  });

  it("copies and pastes nodes with relative offsets, skipping protected nodes", () => {
    useWorkflowStore.setState({ selectedNodeId: "llm" });
    expect(useWorkflowStore.getState().copySelection()).toBe(1);

    const pasted = useWorkflowStore.getState().pasteClipboard({ x: 900, y: 400 });
    expect(pasted).toBe(1);
    const copy = useWorkflowStore.getState().nodes.find((node) => node.type === "llm" && node.id !== "llm");
    expect(copy?.position).toEqual({ x: 900, y: 400 });
    expect(copy?.data.config).toMatchObject({ provider: "p", model: "m" });
  });

  it("selects every node on demand", () => {
    useWorkflowStore.getState().selectAllNodes();
    expect(useWorkflowStore.getState().nodes.every((node) => node.selected)).toBe(true);
  });
});
