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
    });
    resolveRequest?.({ session_id: "session-new", messages: [] });
    await loading;
  });
});
