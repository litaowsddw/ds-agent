import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MessageBubble, { formatChatTime } from "@/components/chat/MessageBubble";
import { showToast } from "@/components/layout/AppLayout";
import type { Message } from "@/stores/chat";

vi.mock("@/components/layout/AppLayout", () => ({ showToast: vi.fn() }));

const assistantMessage: Message = {
  message_id: "message-1",
  role: "assistant",
  content: "这是回答",
  sequence: 1,
  created_at: "2026-07-12T01:30:00.000Z",
};

describe("MessageBubble", () => {
  beforeEach(() => {
    vi.mocked(showToast).mockReset();
  });

  it("uses a Chinese localized time label", () => {
    render(<MessageBubble message={assistantMessage} />);

    expect(screen.getByText(formatChatTime(assistantMessage.created_at))).toBeInTheDocument();
    expect(formatChatTime(assistantMessage.created_at)).toContain("09:30");
  });

  it("copies assistant text and confirms success with Toast", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<MessageBubble message={assistantMessage} />);

    fireEvent.click(screen.getByRole("button", { name: "复制回答" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("这是回答"));
    expect(showToast).toHaveBeenCalledWith("success", "回答已复制");
  });

  it("reports clipboard failures with Toast", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    render(<MessageBubble message={assistantMessage} />);

    fireEvent.click(screen.getByRole("button", { name: "复制回答" }));

    await waitFor(() => expect(showToast).toHaveBeenCalledWith("error", "复制失败，请手动复制"));
  });
});
