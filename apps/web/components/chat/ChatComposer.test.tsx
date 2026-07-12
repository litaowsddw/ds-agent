import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChatComposer from "@/components/chat/ChatComposer";

describe("ChatComposer", () => {
  it("sends with Enter and keeps a controlled Shift+Enter newline", () => {
    const onSend = vi.fn();
    render(<ChatComposer disabled={false} onSend={onSend} />);
    const textbox = screen.getByRole("textbox", { name: "消息" });
    fireEvent.change(textbox, { target: { value: "你好" } });
    fireEvent.keyDown(textbox, { key: "Enter", shiftKey: true });
    fireEvent.change(textbox, { target: { value: "你好\n世界" } });
    expect(textbox).toHaveValue("你好\n世界");
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("你好\n世界");
  });

  it("blocks retry and explains when the captured Workflow is unavailable", () => {
    const onRetry = vi.fn();
    render(
      <ChatComposer
        disabled={false}
        onSend={vi.fn()}
        onRetry={onRetry}
        retryBlockedMessage="上次消息使用的 Workflow 已不可用，请重新选择后发送。"
      />
    );

    expect(screen.getByText("上次消息使用的 Workflow 已不可用，请重新选择后发送。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试上次消息" }));
    expect(onRetry).not.toHaveBeenCalled();
  });

  it("allows snapshot retry when only new sends are blocked", () => {
    const onRetry = vi.fn();
    render(
      <ChatComposer
        disabled
        retryDisabled={false}
        onSend={vi.fn()}
        onRetry={onRetry}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "重试上次消息" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
