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
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("hello\nworld");
  });

  it("shows the estimated current-context percentage beside send", () => {
    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        contextUsage={{ usedTokens: 600, limitTokens: 2400 }}
      />
    );

    expect(screen.getByLabelText("当前上下文占比")).toHaveTextContent("600 / 2,400 · 25%");
  });

  it("allows snapshot retry when only new sends are blocked", () => {
    const onRetry = vi.fn();
    render(<ChatComposer disabled retryDisabled={false} onSend={vi.fn()} onRetry={onRetry} />);

    fireEvent.click(screen.getByRole("button", { name: "重试上次消息" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
