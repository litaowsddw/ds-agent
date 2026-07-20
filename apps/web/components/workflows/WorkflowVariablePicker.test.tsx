import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WorkflowVariablePicker, {
  appendWorkflowReference,
  directUpstreamNodes,
} from "@/components/workflows/WorkflowVariablePicker";

const nodes = [
  { id: "start", type: "start", data: { label: "Start" } },
  {
    id: "retrieve_policy",
    type: "rag",
    data: { label: "Knowledge retrieval", config: { display_name: "Refund policy" } },
  },
  { id: "answer", type: "llm", data: { label: "Answer" } },
];

const edges = [
  { source: "start", target: "retrieve_policy" },
  { source: "retrieve_policy", target: "answer" },
];

describe("WorkflowVariablePicker", () => {
  it("offers only executor-supported RAG templates and inserts the selected value", () => {
    const onInsert = vi.fn();
    render(
      <WorkflowVariablePicker
        edges={edges}
        nodeId="answer"
        nodes={nodes}
        onInsert={onInsert}
      />
    );

    expect(screen.getByRole("region", { name: "Available workflow variables" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "{{input.text}}" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "{{upstream}}" })).toBeInTheDocument();
    expect(screen.getByText("upstream.retrieve_policy")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "{{upstream.retrieve_policy}}" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "{{input.text}}" }));

    expect(onInsert).toHaveBeenCalledWith("{{input.text}}");
  });

  it("derives direct upstream output paths and avoids duplicating inserted templates", () => {
    expect(directUpstreamNodes(nodes, edges, "answer").map((node) => node.id)).toEqual([
      "retrieve_policy",
    ]);
    expect(appendWorkflowReference("Find policy", "{{input.text}}")).toBe(
      "Find policy {{input.text}}"
    );
    expect(appendWorkflowReference("Find {{input.text}}", "{{input.text}}")).toBe(
      "Find {{input.text}}"
    );
  });
});
