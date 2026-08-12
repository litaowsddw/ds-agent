import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChatPanel from "@/components/chat/ChatPanel";
import type { Agent } from "@/types/agent";

const { chatState } = vi.hoisted(() => ({
  chatState: {
    agentId: "agent-old" as string,
    sessionId: null as string | null,
    sessions: [] as Array<{
      session_id: string;
      status: string;
      compact_summary: string;
      created_at: string;
      updated_at: string;
    }>,
    messages: [
      {
        message_id: "old-message",
        role: "assistant" as const,
        content: "旧 Agent 消息不得闪现",
        sequence: 0,
        created_at: "2026-07-12T01:00:00Z",
      },
    ],
    traceEvents: [],
    isGenerating: false,
    isLoadingSession: false,
    intent: "旧意图",
    subtaskCount: 9,
    failedSendSnapshot: null,
    sendMessage: vi.fn(),
    retryLastMessage: vi.fn(),
    cancelGeneration: vi.fn(),
    loadLatestSession: vi.fn(),
    loadSessionHistory: vi.fn(),
    loadMessages: vi.fn(),
    clearSession: vi.fn(),
  },
}));

vi.mock("@/stores/chat", () => ({
  useChatStore: (selector?: (state: typeof chatState) => unknown) =>
    selector ? selector(chatState) : chatState,
}));

function agent(agentId: string): Agent {
  return {
    agent_id: agentId,
    org_id: "org-a",
    team_id: null,
    name: agentId,
    description: "",
    created_by: "user-a",
  };
}

describe("ChatPanel Agent rendering gate", () => {
  it("shows saved conversations and loads the selected session", async () => {
    Element.prototype.scrollIntoView = vi.fn();
    chatState.agentId = "agent-old";
    chatState.sessionId = "session-current";
    chatState.sessions = [
      {
        session_id: "session-current",
        status: "idle",
        compact_summary: "Current planning discussion",
        created_at: "2026-07-12T01:00:00Z",
        updated_at: "2026-07-12T02:00:00Z",
      },
      {
        session_id: "session-earlier",
        status: "idle",
        compact_summary: "Earlier discussion",
        created_at: "2026-07-11T01:00:00Z",
        updated_at: "2026-07-11T02:00:00Z",
      },
    ];
    render(
      <ChatPanel
        agentId="agent-old"
        orgId="org-a"
        actorUserId="user-a"
        workflows={[]}
        agent={agent("agent-old")}
      />
    );

    const history = screen.getByLabelText("会话历史");
    expect(history).toHaveValue("session-current");
    expect(screen.getByRole("option", { name: "Earlier discussion" })).toBeInTheDocument();
    fireEvent.change(history, { target: { value: "session-earlier" } });
    expect(chatState.loadMessages).toHaveBeenCalledWith("session-earlier");
  });

  it("hides old messages in the same render that switches the Agent prop", () => {
    Element.prototype.scrollIntoView = vi.fn();
    const { rerender } = render(
      <ChatPanel
        agentId="agent-old"
        orgId="org-a"
        actorUserId="user-a"
        workflows={[]}
        agent={agent("agent-old")}
      />
    );
    expect(screen.getByText("旧 Agent 消息不得闪现")).toBeInTheDocument();
    expect(screen.getByText("意图：旧意图 · 子任务：9")).toBeInTheDocument();

    rerender(
      <ChatPanel
        agentId="agent-new"
        orgId="org-a"
        actorUserId="user-a"
        workflows={[]}
        agent={agent("agent-new")}
      />
    );

    expect(screen.queryByText("旧 Agent 消息不得闪现")).not.toBeInTheDocument();
    expect(screen.queryByText("意图：旧意图 · 子任务：9")).not.toBeInTheDocument();
  });

  it("shows a loading state instead of the previous session while a selected session loads", () => {
    chatState.agentId = "agent-old";
    chatState.messages = [];
    chatState.isLoadingSession = true;
    render(
      <ChatPanel
        agentId="agent-old"
        orgId="org-a"
        actorUserId="user-a"
        workflows={[]}
        agent={agent("agent-old")}
      />
    );

    expect(screen.getByText("正在加载会话…")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeDisabled();
    chatState.isLoadingSession = false;
  });
});
