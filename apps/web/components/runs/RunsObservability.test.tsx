import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import JsonDisclosure from "@/components/runs/JsonDisclosure";
import NodeRunCard, { formatElapsed } from "@/components/runs/NodeRunCard";
import RunList from "@/components/runs/RunList";
import RunStatusBadge from "@/components/runs/RunStatusBadge";
import RunSummary from "@/components/runs/RunSummary";
import type { NodeRun, WorkflowRun } from "@/types/workflow";

const runs: WorkflowRun[] = [
  {
    run_id: "run-failed",
    workflow_id: "workflow-orders",
    version_id: "version-2",
    agent_id: "agent-a",
    status: "failed",
    output_data: { partial: true },
    error_message: "Payment node failed",
    created_at: "2026-07-12T01:00:00Z",
    updated_at: "2026-07-12T01:00:01Z",
  },
  {
    run_id: "run-ok",
    workflow_id: "workflow-support",
    version_id: "version-1",
    agent_id: "agent-a",
    status: "succeeded",
    output_data: { answer: "done" },
    error_message: "",
    created_at: "2026-07-12T02:00:00Z",
    updated_at: "2026-07-12T02:00:02Z",
  },
];

describe("RunStatusBadge", () => {
  it.each([
    ["pending", "待处理"],
    ["running", "运行中"],
    ["succeeded", "成功"],
    ["failed", "失败"],
    ["canceled", "已取消"],
    ["timeout", "超时"],
    ["skipped", "已跳过"],
  ])("renders legal status %s semantically", (status, label) => {
    render(<RunStatusBadge status={status} />);

    expect(screen.getByText(label)).not.toHaveAttribute("data-tone", "neutral");
  });

  it("renders only unknown statuses neutrally", () => {
    render(<RunStatusBadge status="paused-by-provider" />);

    expect(screen.getByText("paused-by-provider")).toHaveAttribute("data-tone", "neutral");
  });
});

describe("RunList", () => {
  it("filters runs by status and exposes workflow labels", () => {
    render(
      <RunList
        runs={runs}
        selectedRunId=""
        onSelect={vi.fn()}
        workflowLabels={{ "workflow-orders": "订单处理" }}
      />
    );

    expect(screen.getByText("工作流 订单处理")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("按状态筛选运行"), {
      target: { value: "failed" },
    });

    expect(screen.getByText("run-failed")).toBeInTheDocument();
    expect(screen.queryByText("run-ok")).not.toBeInTheDocument();
  });
});

describe("RunSummary", () => {
  it("shows failures before output and uses a dash for missing values", () => {
    const missingRun: WorkflowRun = {
      ...runs[0],
      version_id: "",
      created_at: "",
      updated_at: null,
    };
    const { container } = render(<RunSummary run={missingRun} />);

    expect(screen.getByText("Payment node failed")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    const text = container.textContent ?? "";
    expect(text.indexOf("Payment node failed")).toBeLessThan(text.indexOf("输出"));
  });
});

describe("NodeRunCard", () => {
  it("formats durations and keeps unknown node data neutral", () => {
    expect(formatElapsed(1530)).toBe("1.53 秒");
    const nodeRun: NodeRun = {
      node_run_id: "node-run-1",
      node_id: "",
      node_type: "custom",
      status: "mystery",
      input_data: {},
      output_data: {},
      error_message: "",
      elapsed_ms: Number.NaN,
    };

    render(<NodeRunCard nodeRun={nodeRun} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText("mystery")).toHaveAttribute("data-tone", "neutral");
  });
});

describe("JsonDisclosure", () => {
  it("uses an accessible details disclosure for raw JSON", () => {
    render(<JsonDisclosure label="原始输出" value={{ ok: true }} />);

    const disclosure = screen.getByText("原始输出").closest("details");
    expect(disclosure).not.toBeNull();
    expect(within(disclosure as HTMLElement).getByText(/"ok": true/)).toBeInTheDocument();
  });

  it("uses a dash when raw data is missing", () => {
    render(<JsonDisclosure label="原始输出" value={undefined} />);

    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
