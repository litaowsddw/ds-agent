import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ChatComposer from "@/components/chat/ChatComposer";
import { useChatStore } from "@/stores/chat";

describe("ChatComposer", () => {
  afterEach(() => {
    useChatStore.setState({ actualContextUsage: null });
  });

  it("sends with Enter and keeps a controlled Shift+Enter newline", () => {
    const onSend = vi.fn();
    render(<ChatComposer disabled={false} onSend={onSend} />);
    const textbox = screen.getByRole("textbox");
    fireEvent.change(textbox, { target: { value: "hello" } });
    fireEvent.keyDown(textbox, { key: "Enter", shiftKey: true });
    fireEvent.change(textbox, { target: { value: "hello\nworld" } });
    expect(textbox).toHaveValue("hello\nworld");
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("hello\nworld");
  });

  it("shows provider-reported input tokens and cache tokens", () => {
    const { container } = render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        contextUsage={{
          inputTokens: 1250,
          outputTokens: 80,
          contextTokens: 1330,
          outputTokenStatus: "provider_final",
          cacheReadInputTokens: 640,
          limitTokens: 2400,
          usageStatus: "provider_final",
          preflightInputTokens: 1248,
          stablePrefixTokens: 960,
          tokenizerStatus: "official_tokenizer",
          tokenizer: "deepseek-v3-official",
          promptBreakdown: [
            { key: "system", label: "System prompt", tokens: 250 },
            { key: "tools", label: "Tools / Skills", tokens: 998 },
          ],
          calibrationStatus: "provider_final",
          activeWorkflowNodeId: null,
        }}
      />
    );

    expect(container.textContent).toContain("1,330");
    expect(container.textContent).toContain("上下文 1,330 / 2,400 · 55%");
    expect(container.textContent).toContain("输入 1,250 · 输出 80");
    expect(container.textContent).toContain("640");
    expect(container.textContent).not.toContain("estimate");
  });

  it("does not invent a token count when the provider did not report usage", () => {
    const { container } = render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        contextUsage={{
          inputTokens: null,
          outputTokens: 0,
          contextTokens: null,
          outputTokenStatus: "unavailable",
          cacheReadInputTokens: null,
          limitTokens: 2400,
          usageStatus: "unavailable",
          preflightInputTokens: null,
          stablePrefixTokens: null,
          tokenizerStatus: "characters_divided_by_4",
          tokenizer: null,
          promptBreakdown: [],
          calibrationStatus: "unavailable",
          activeWorkflowNodeId: null,
        }}
      />
    );

    expect(container.textContent).not.toContain("2,400 ·");
  });

  it("keeps the idle placeholder neutral before any context usage event", () => {
    useChatStore.setState({ actualContextUsage: null });

    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        contextUsage={{
          inputTokens: null,
          outputTokens: 0,
          contextTokens: null,
          outputTokenStatus: "unavailable",
          cacheReadInputTokens: null,
          limitTokens: 2400,
          usageStatus: "unavailable",
          preflightInputTokens: null,
          stablePrefixTokens: null,
          tokenizerStatus: "characters_divided_by_4",
          tokenizer: null,
          promptBreakdown: [],
        }}
      />
    );

    expect(screen.queryByText("Provider 未提供用量")).not.toBeInTheDocument();
  });

  it.each([
    ["estimated", "实时估算"],
    ["partially_calibrated", "部分已校准"],
    ["provider_final", "Provider 已校准"],
    ["unavailable", "Provider 未提供用量"],
  ] as const)("shows the %s calibration label", (calibrationStatus, label) => {
    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        contextUsage={{
          inputTokens: calibrationStatus === "unavailable" ? null : 100,
          outputTokens: calibrationStatus === "unavailable" ? 0 : 20,
          contextTokens: calibrationStatus === "unavailable" ? null : 120,
          outputTokenStatus: calibrationStatus === "provider_final" ? "provider_final" : "unavailable",
          cacheReadInputTokens: null,
          limitTokens: 2400,
          usageStatus: calibrationStatus === "provider_final" ? "provider_final" : "unavailable",
          preflightInputTokens: calibrationStatus === "unavailable" ? null : 100,
          stablePrefixTokens: null,
          tokenizerStatus: "characters_divided_by_4",
          tokenizer: null,
          promptBreakdown: [],
          calibrationStatus,
          activeWorkflowNodeId: calibrationStatus === "estimated" ? "llm-a" : null,
        }}
      />
    );

    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("shows the active Workflow node", () => {
    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        contextUsage={{
          inputTokens: 100,
          outputTokens: 20,
          contextTokens: 120,
          outputTokenStatus: "characters_divided_by_4",
          cacheReadInputTokens: null,
          limitTokens: 2400,
          usageStatus: "unavailable",
          preflightInputTokens: 100,
          stablePrefixTokens: null,
          tokenizerStatus: "characters_divided_by_4",
          tokenizer: null,
          promptBreakdown: [],
          calibrationStatus: "estimated",
          activeWorkflowNodeId: "llm-a",
        }}
      />
    );

    expect(screen.getByText("当前节点：llm-a")).toBeInTheDocument();
  });

  it("uses live calibration metadata when the host passes legacy usage props", () => {
    useChatStore.setState({
      actualContextUsage: {
        inputTokens: 100,
        outputTokens: 20,
        contextTokens: 120,
        outputTokenStatus: "characters_divided_by_4",
        cacheReadInputTokens: null,
        tokenLimit: 2400,
        usageStatus: "unavailable",
        preflightInputTokens: 100,
        stablePrefixTokens: null,
        tokenizerStatus: "characters_divided_by_4",
        tokenizer: null,
        promptBreakdown: [],
        calibrationStatus: "estimated",
        activeWorkflowNodeId: "llm-a",
      },
    });

    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        contextUsage={{
          inputTokens: 100,
          outputTokens: 20,
          contextTokens: 120,
          outputTokenStatus: "characters_divided_by_4",
          cacheReadInputTokens: null,
          limitTokens: 2400,
          usageStatus: "unavailable",
          preflightInputTokens: 100,
          stablePrefixTokens: null,
          tokenizerStatus: "characters_divided_by_4",
          tokenizer: null,
          promptBreakdown: [],
        } as never}
      />
    );

    expect(screen.getByText("实时估算")).toBeInTheDocument();
    expect(screen.getByText("当前节点：llm-a")).toBeInTheDocument();
  });
});
