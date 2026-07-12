import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChatPanel from "@/components/chat/ChatPanel";
import type { Agent } from "@/types/agent";

const { chatState } = vi.hoisted(() => ({
  chatState: {
    agentId: "agent-old",
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
    intent: "旧意图",
    subtaskCount: 9,
    failedSendSnapshot: null,
    sendMessage: vi.fn(),
    retryLastMessage: vi.fn(),
    loadLatestSession: vi.fn(),
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
});
