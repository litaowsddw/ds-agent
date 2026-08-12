/** Client-side preflight checklist mirroring the publish-time validator rules. */

import type { Edge, Node } from "@xyflow/react";
import type { CustomNodeData } from "@/types/workflow";

export interface ChecklistIssue {
  nodeId: string | null;
  message: string;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function runWorkflowChecklist(
  nodes: Node<CustomNodeData>[],
  edges: Edge[]
): ChecklistIssue[] {
  const issues: ChecklistIssue[] = [];
  const nodeLabel = (node: Node<CustomNodeData>) => {
    const display = text(node.data.config?.display_name);
    return display || node.data.label || node.id;
  };

  for (const node of nodes) {
    const config = node.data.config ?? {};
    switch (node.type) {
      case "llm":
        if (!text(config.provider) || !text(config.model)) {
          issues.push({ nodeId: node.id, message: `「${nodeLabel(node)}」未选择模型提供方或模型` });
        }
        break;
      case "rag":
        if (!text(config.kb_id)) {
          issues.push({ nodeId: node.id, message: `「${nodeLabel(node)}」未选择知识库` });
        }
        break;
      case "tool":
        if (!text(config.tool_id)) {
          issues.push({ nodeId: node.id, message: `「${nodeLabel(node)}」未选择工具` });
        }
        break;
      case "condition": {
        if (!text(config.left)) {
          issues.push({ nodeId: node.id, message: `「${nodeLabel(node)}」未配置判断数据` });
        }
        const branches = new Set(
          edges.filter((edge) => edge.source === node.id).map((edge) => edge.sourceHandle)
        );
        if (!branches.has("true") || !branches.has("false")) {
          issues.push({ nodeId: node.id, message: `「${nodeLabel(node)}」需要同时连接 true 和 false 分支` });
        }
        break;
      }
      default:
        break;
    }
  }

  const start = nodes.find((node) => node.type === "start");
  const end = nodes.find((node) => node.type === "end");
  if (start && !edges.some((edge) => edge.source === start.id)) {
    issues.push({ nodeId: start.id, message: "Start 节点没有任何输出连线" });
  }
  if (start && end) {
    const reachable = new Set<string>([start.id]);
    const queue = [start.id];
    while (queue.length > 0) {
      const current = queue.shift() as string;
      for (const edge of edges) {
        if (edge.source === current && !reachable.has(edge.target)) {
          reachable.add(edge.target);
          queue.push(edge.target);
        }
      }
    }
    if (!reachable.has(end.id)) {
      issues.push({ nodeId: end.id, message: "End 节点无法从 Start 节点到达" });
    }
    for (const node of nodes) {
      if (node.id !== start.id && !reachable.has(node.id)) {
        issues.push({ nodeId: node.id, message: `「${nodeLabel(node)}」无法从 Start 节点到达` });
      }
    }
  }
  return issues;
}
