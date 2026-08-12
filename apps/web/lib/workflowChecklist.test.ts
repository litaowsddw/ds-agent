import { describe, expect, it } from "vitest";
import { runWorkflowChecklist } from "@/lib/workflowChecklist";
import type { CustomNodeData } from "@/types/workflow";
import type { Edge, Node } from "@xyflow/react";

function node(id: string, type: string, config: Record<string, unknown> = {}): Node<CustomNodeData> {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: { label: type, config },
  };
}

function edge(source: string, target: string, sourceHandle?: string): Edge {
  return { id: `${source}-${target}-${sourceHandle ?? "main"}`, source, target, sourceHandle };
}

describe("runWorkflowChecklist", () => {
  it("passes a fully configured linear workflow", () => {
    const issues = runWorkflowChecklist(
      [
        node("start", "start"),
        node("llm", "llm", { provider: "p", model: "m" }),
        node("end", "end"),
      ],
      [edge("start", "llm"), edge("llm", "end")]
    );
    expect(issues).toEqual([]);
  });

  it("flags unconfigured nodes and unreachable ends", () => {
    const issues = runWorkflowChecklist(
      [
        node("start", "start"),
        node("llm", "llm"),
        node("rag", "rag"),
        node("end", "end"),
      ],
      [edge("start", "llm")]
    );
    const messages = issues.map((issue) => issue.message).join("\n");
    expect(messages).toContain("未选择模型提供方或模型");
    expect(messages).toContain("未选择知识库");
    expect(messages).toContain("无法从 Start 节点到达");
  });

  it("requires both condition branches", () => {
    const issues = runWorkflowChecklist(
      [
        node("start", "start"),
        node("check", "condition", { left: "{{input.text}}", operator: "exists" }),
        node("end", "end"),
      ],
      [edge("start", "check"), edge("check", "end", "true")]
    );
    expect(issues.some((issue) => issue.message.includes("true 和 false 分支"))).toBe(true);
  });
});
