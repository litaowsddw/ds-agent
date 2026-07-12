import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ThinkingTrace from "@/components/chat/ThinkingTrace";
import type { ChatTraceEvent } from "@/stores/chat";

function event(index: number, overrides: Partial<ChatTraceEvent> = {}): ChatTraceEvent {
  return {
    id: `event-${index}`,
    event: "node_finished",
    node: `node-${index}`,
    label: `步骤 ${index}`,
    status: "succeeded",
    data: {},
    created_at: `2026-07-12T01:00:0${index}.000Z`,
    ...overrides,
  };
}

describe("ThinkingTrace", () => {
  it("shows only the latest five events until expanded", () => {
    render(<ThinkingTrace events={Array.from({ length: 7 }, (_, index) => event(index + 1))} />);

    expect(screen.queryByText("步骤 1")).not.toBeInTheDocument();
    expect(screen.getByText("步骤 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开全部 7 条" }));
    expect(screen.getByText("步骤 1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "收起执行 Trace" }));
    expect(screen.queryByText("步骤 1")).not.toBeInTheDocument();
  });

  it("announces running and failed states in Chinese", () => {
    const { rerender } = render(
      <ThinkingTrace events={[event(1, { event: "node_started", status: "running" })]} />
    );
    expect(screen.getByText("执行中")).toBeInTheDocument();

    rerender(
      <ThinkingTrace
        events={[event(2, { event: "error", status: "failed", data: { error: "模型不可用" } })]}
      />
    );
    expect(screen.getByText("执行失败")).toBeInTheDocument();
    expect(screen.getByText("模型不可用")).toBeInTheDocument();
  });
});
