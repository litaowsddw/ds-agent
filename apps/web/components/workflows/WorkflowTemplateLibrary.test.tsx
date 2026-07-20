import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WorkflowTemplateLibrary from "@/components/workflows/WorkflowTemplateLibrary";
import { WORKFLOW_TEMPLATES } from "@/components/workflows/workflowTemplates";

describe("WorkflowTemplateLibrary", () => {
  it("makes executable templates and required tenant setup visible before copying", () => {
    render(<WorkflowTemplateLibrary onSelect={vi.fn()} />);

    expect(screen.getByRole("region", { name: "Workflow templates" })).toHaveTextContent(
      "不会覆盖当前 Workflow，也不会改动任何已发布版本"
    );
    expect(screen.getByText("客户支持助手")).toBeInTheDocument();
    expect(screen.getByText("知识库问答")).toBeInTheDocument();
    expect(screen.getByText("选择一个知识库")).toBeInTheDocument();
  });

  it("passes the selected template to the canvas owner", () => {
    const onSelect = vi.fn();
    render(<WorkflowTemplateLibrary onSelect={onSelect} />);

    fireEvent.click(screen.getAllByRole("button", { name: "使用此模板" })[1]);

    expect(onSelect).toHaveBeenCalledWith(WORKFLOW_TEMPLATES[1]);
  });
});
