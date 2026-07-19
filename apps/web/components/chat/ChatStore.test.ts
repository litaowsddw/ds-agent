import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "@/lib/api";
import { useChatStore, type SendMessageOptions } from "@/stores/chat";

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://api.test",
  apiRequest: vi.fn(),
  getAccessToken: vi.fn(() => null),
  getCurrentOrgId: vi.fn(() => null),
}));
vi.mock("@/lib/websocket", () => ({ wsManager: { on: vi.fn(() => vi.fn()) } }));

function successfulStream(): Response {
  const chunks = [
    new TextEncoder().encode(
      'event: run_finished\ndata: {"session_id":"session-new"}\n\n'
    ),
  ];
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: vi.fn().mockResolvedValueOnce({ done: false, value: chunks[0] }).mockResolvedValueOnce({ done: true }),
      }),
    },
  } as unknown as Response;
}

function streamWithFrames(frames: string): Response {
  const chunk = new TextEncoder().encode(frames);
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: vi.fn().mockResolvedValueOnce({ done: false, value: chunk }).mockResolvedValueOnce({ done: true }),
      }),
    },
  } as unknown as Response;
}

function delayedStream() {
  let release: ((result: { done: false; value: Uint8Array }) => void) | undefined;
  const read = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<{ done: false; value: Uint8Array }>((resolve) => {
          release = resolve;
        })
    )
    .mockResolvedValueOnce({ done: true });
  return {
    response: { ok: true, body: { getReader: () => ({ read }) } } as unknown as Response,
    emit(frames: string) {
      if (!release) throw new Error("stream reader is not waiting");
      release({ done: false, value: new TextEncoder().encode(frames) });
    },
    read,
  };
}

describe("chat store retry safety", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useChatStore.setState({
      sessionId: null,
      messages: [],
      traceEvents: [],
      isGenerating: false,
      agentId: null,
      intent: "",
      subtaskCount: 0,
      failedSendSnapshot: null,
      actualContextUsage: null,
    });
  });

  it("retains an immutable failure snapshot and retries the original mode and Workflow", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(successfulStream()));
    const options: SendMessageOptions = { executionMode: "workflow", workflowId: "workflow-original" };

    await useChatStore.getState().sendMessage("agent-a", "org-a", "原始消息", "user-a", options);
    options.executionMode = "autonomous";
    options.workflowId = "workflow-changed";

    expect(useChatStore.getState().failedSendSnapshot).toEqual({
      agentId: "agent-a",
      orgId: "org-a",
      actorUserId: "user-a",
      message: "原始消息",
      options: { executionMode: "workflow", workflowId: "workflow-original" },
    });

    await useChatStore.getState().retryLastMessage();
    const secondRequest = vi.mocked(fetch).mock.calls[1]?.[1];
    expect(JSON.parse(String(secondRequest?.body))).toMatchObject({
      message: "原始消息",
      execution_mode: "workflow",
      workflow_id: "workflow-original",
    });
    expect(JSON.parse(String(secondRequest?.body))).not.toHaveProperty("org_id");
    expect(JSON.parse(String(secondRequest?.body))).not.toHaveProperty("actor_user_id");
    expect(useChatStore.getState().failedSendSnapshot).toBeNull();
  });

  it("clears the previous Agent messages before awaiting the next session", async () => {
    let resolveRequest: ((value: { session_id: string; messages: [] }) => void) | undefined;
    vi.mocked(apiRequest).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveRequest = resolve;
      })
    );
    useChatStore.setState({
      agentId: "agent-old",
      sessionId: "session-old",
      intent: "旧意图",
      subtaskCount: 4,
      messages: [
        {
          message_id: "old",
          role: "assistant",
          content: "旧 Agent 消息",
          sequence: 0,
          created_at: "2026-07-12T01:00:00Z",
        },
      ],
      traceEvents: [
        {
          id: "old-trace",
          event: "node_started",
          status: "running",
          data: {},
          created_at: "2026-07-12T01:00:00Z",
        },
      ],
    });

    const loading = useChatStore.getState().loadLatestSession("agent-new", "user-a");
    expect(useChatStore.getState()).toMatchObject({
      agentId: "agent-new",
      sessionId: null,
      messages: [],
      traceEvents: [],
      intent: "",
      subtaskCount: 0,
    });
    resolveRequest?.({ session_id: "session-new", messages: [] });
    await loading;
  });

  it("clears a generating session immediately and ignores its late stream completion", async () => {
    const oldStream = delayedStream();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(oldStream.response));
    const oldSend = useChatStore.getState().sendMessage("agent-a", "org-a", "旧请求", "user-a");
    await vi.waitFor(() => expect(oldStream.read).toHaveBeenCalled());
    useChatStore.setState({
      sessionId: "session-old",
      traceEvents: [
        {
          id: "trace-old",
          event: "node_started",
          status: "running",
          data: {},
          created_at: "2026-07-12T01:00:00Z",
        },
      ],
      failedSendSnapshot: {
        agentId: "agent-a",
        orgId: "org-a",
        actorUserId: "user-a",
        message: "旧请求",
        options: { executionMode: "autonomous" },
      },
    });

    useChatStore.getState().clearSession();
    expect(useChatStore.getState()).toMatchObject({
      sessionId: null,
      messages: [],
      traceEvents: [],
      isGenerating: false,
      failedSendSnapshot: null,
      intent: "",
      subtaskCount: 0,
    });

    oldStream.emit(
      'event: token\ndata: {"text":"旧 token"}\n\n' +
        'event: run_finished\ndata: {"session_id":"session-late"}\n\n'
    );
    await oldSend;
    expect(useChatStore.getState()).toMatchObject({
      sessionId: null,
      messages: [],
      traceEvents: [],
      isGenerating: false,
      failedSendSnapshot: null,
    });
  });

  it("ignores every late token, error, completion and final write from the previous Agent stream", async () => {
    const oldStream = delayedStream();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(oldStream.response));
    const oldSend = useChatStore.getState().sendMessage("agent-old", "org-a", "旧请求", "user-a");
    await vi.waitFor(() => expect(oldStream.read).toHaveBeenCalled());
    const oldAssistantId = useChatStore.getState().messages[1].message_id;
    vi.mocked(apiRequest).mockResolvedValueOnce({
      session_id: "session-new",
      messages: [
        {
          message_id: oldAssistantId,
          role: "assistant",
          content: "新 Agent 回答",
          sequence: 0,
          created_at: "2026-07-12T02:00:00Z",
        },
      ],
    });

    await useChatStore.getState().loadLatestSession("agent-new", "user-a");
    useChatStore.setState({ isGenerating: true });
    oldStream.emit(
      'event: token\ndata: {"text":"旧 token"}\n\n' +
        'event: error\ndata: {"error":"旧错误"}\n\n' +
        'event: run_finished\ndata: {"session_id":"session-old-finished"}\n\n'
    );
    await oldSend;

    expect(useChatStore.getState()).toMatchObject({
      agentId: "agent-new",
      sessionId: "session-new",
      isGenerating: true,
      failedSendSnapshot: null,
      traceEvents: [],
      messages: [expect.objectContaining({ content: "新 Agent 回答", role: "assistant" })],
    });
  });

  it("terminates running Trace entries as failed when an SSE error arrives", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamWithFrames(
          'event: node_started\ndata: {"node":"model","label":"调用模型"}\n\n' +
            'event: error\ndata: {"error":"模型不可用"}\n\n'
        )
      )
    );

    await useChatStore.getState().sendMessage("agent-a", "org-a", "你好", "user-a");

    expect(useChatStore.getState().traceEvents).toEqual([
      expect.objectContaining({ node: "model", status: "failed" }),
      expect.objectContaining({ event: "error", status: "failed" }),
    ]);
  });

  it("uses a Chinese HTTP error while retaining response detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, statusText: "Bad Gateway", body: {} } as Response)
    );

    await useChatStore.getState().sendMessage("agent-a", "org-a", "你好", "user-a");

    expect(useChatStore.getState().messages.at(-1)?.content).toBe("请求失败：Bad Gateway");
  });

  it("uses a Chinese SSE fallback and keeps backend error detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(streamWithFrames("event: error\ndata: {}\n\n"))
        .mockResolvedValueOnce(streamWithFrames('event: error\ndata: {"error":"provider detail"}\n\n'))
    );

    await useChatStore.getState().sendMessage("agent-a", "org-a", "第一次", "user-a");
    expect(useChatStore.getState().messages.at(-1)?.content).toBe("对话失败");
    await useChatStore.getState().sendMessage("agent-a", "org-a", "第二次", "user-a");
    expect(useChatStore.getState().messages.at(-1)?.content).toBe("对话失败：provider detail");
  });

  it("aggregates workflow usage by call and keeps mixed calibration explicit", async () => {
    const usageUpdates: Array<NonNullable<ReturnType<typeof useChatStore.getState>["actualContextUsage"]>> = [];
    const unsubscribe = useChatStore.subscribe((state) => {
      if (state.actualContextUsage) usageUpdates.push(state.actualContextUsage);
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamWithFrames(
          'event: context_preflight\ndata: {"usage_key":"run:llm-a","usage_scope":"workflow","workflow_node_id":"llm-a","input_tokens":100,"usage_phase":"preflight"}\n\n' +
            'event: context_progress\ndata: {"usage_key":"run:llm-a","usage_scope":"workflow","workflow_node_id":"llm-a","output_tokens":20,"context_tokens":120,"usage_phase":"estimated"}\n\n' +
            'event: context_usage\ndata: {"usage_key":"run:llm-a","usage_scope":"workflow","workflow_node_id":"llm-a","input_tokens":110,"output_tokens":22,"usage_phase":"provider_final","usage_status":"provider_final"}\n\n' +
            'event: context_preflight\ndata: {"usage_key":"run:llm-b","usage_scope":"workflow","workflow_node_id":"llm-b","input_tokens":200,"usage_phase":"preflight"}\n\n' +
            'event: context_progress\ndata: {"usage_key":"run:llm-b","usage_scope":"workflow","workflow_node_id":"llm-b","output_tokens":10,"usage_phase":"estimated"}\n\n'
        )
      )
    );

    await useChatStore.getState().sendMessage("agent-a", "org-a", "你好", "user-a");
    unsubscribe();

    expect(usageUpdates).toContainEqual(expect.objectContaining({
      contextTokens: 120,
      calibrationStatus: "estimated",
      activeWorkflowNodeId: "llm-a",
    }));
    expect(usageUpdates).toContainEqual(expect.objectContaining({
      contextTokens: 132,
      calibrationStatus: "provider_final",
      activeWorkflowNodeId: null,
    }));
    expect(useChatStore.getState().actualContextUsage).toMatchObject({
      inputTokens: 310,
      outputTokens: 32,
      contextTokens: 342,
      calibrationStatus: "partially_calibrated",
      activeWorkflowNodeId: "llm-b",
    });
  });

  it("keeps the most recently progressed Workflow node active", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamWithFrames(
          'event: context_progress\ndata: {"usage_key":"run:llm-a","usage_scope":"workflow","workflow_node_id":"llm-a","input_tokens":100,"output_tokens":20,"usage_phase":"estimated"}\n\n' +
            'event: context_preflight\ndata: {"usage_key":"run:llm-b","usage_scope":"workflow","workflow_node_id":"llm-b","input_tokens":200,"usage_phase":"preflight"}\n\n'
        )
      )
    );

    await useChatStore.getState().sendMessage("agent-a", "org-a", "你好", "user-a");

    expect(useChatStore.getState().actualContextUsage).toMatchObject({
      activeWorkflowNodeId: "llm-a",
    });
  });
});
