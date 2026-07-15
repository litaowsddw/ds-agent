import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChatComposer from "@/components/chat/ChatComposer";

describe("ChatComposer", () => {
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
          cacheReadInputTokens: 640,
          limitTokens: 2400,
          usageStatus: "provider_final",
        }}
      />
    );

    expect(container.textContent).toContain("1,250");
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
          cacheReadInputTokens: null,
          limitTokens: 2400,
          usageStatus: "unavailable",
        }}
      />
    );

    expect(container.textContent).not.toContain("2,400 ·");
  });
});
