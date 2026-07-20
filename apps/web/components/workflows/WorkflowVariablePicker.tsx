"use client";

import type { CustomNodeData } from "@/types/workflow";

export interface WorkflowReferenceNode {
  id: string;
  type?: string;
  data: CustomNodeData;
}

export interface WorkflowReferenceEdge {
  source: string;
  target: string;
}

export interface WorkflowTemplateReference {
  value: string;
  label: string;
  description: string;
}

/**
 * These are deliberately limited to the substitutions supported by the
 * current RAG executor. Node output field paths are shown as runtime context,
 * rather than being offered as interpolated variables, so an author cannot
 * save a template that looks supported but will be sent to the model verbatim.
 */
export function workflowTemplateReferences(): WorkflowTemplateReference[] {
  return [
    {
      value: "{{input.text}}",
      label: "Input text",
      description: "The text supplied when the workflow run starts.",
    },
    {
      value: "{{input.query}}",
      label: "Input query",
      description: "Uses the run query when your caller provides one.",
    },
    {
      value: "{{workflow_input}}",
      label: "Full run input",
      description: "The complete input object as JSON.",
    },
    {
      value: "{{upstream}}",
      label: "Direct upstream outputs",
      description: "All immediately connected predecessor outputs as JSON.",
    },
  ];
}

function configuredNodeLabel(node: WorkflowReferenceNode): string {
  const config = node.data.config ?? {};
  const displayName = typeof config.display_name === "string" ? config.display_name.trim() : "";
  return displayName || node.data.label || node.id;
}

/** Return only the steps that can actually feed the selected step at runtime. */
export function directUpstreamNodes(
  nodes: WorkflowReferenceNode[],
  edges: WorkflowReferenceEdge[],
  selectedNodeId: string
): WorkflowReferenceNode[] {
  const upstreamIds = new Set(
    edges.filter((edge) => edge.target === selectedNodeId).map((edge) => edge.source)
  );
  return nodes.filter((node) => upstreamIds.has(node.id));
}

export function appendWorkflowReference(value: string, reference: string): string {
  if (!value.trim()) return reference;
  if (value.includes(reference)) return value;
  return `${value}${value.endsWith(" ") || value.endsWith("\n") ? "" : " "}${reference}`;
}

export default function WorkflowVariablePicker({
  edges,
  nodeId,
  nodes,
  onInsert,
}: {
  edges: WorkflowReferenceEdge[];
  nodeId: string;
  nodes: WorkflowReferenceNode[];
  onInsert: (reference: string) => void;
}) {
  const upstream = directUpstreamNodes(nodes, edges, nodeId);

  return (
    <section aria-label="Available workflow variables" className="rounded-lg border border-[#dbeafe] bg-[#f8fbff] p-3">
      <div className="text-xs font-semibold text-[#175cd3]">Available runtime inputs</div>
      <p className="mt-1 text-xs leading-5 text-[#475467]">
        Insert one of these supported templates into the retrieval query. They are resolved before the knowledge search runs.
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {workflowTemplateReferences().map((reference) => (
          <button
            key={reference.value}
            className="rounded-md border border-[#bfdbfe] bg-white px-2 py-1 text-left text-xs text-[#1d4ed8] transition hover:bg-[#dbeafe]"
            onClick={() => onInsert(reference.value)}
            title={reference.description}
            type="button"
          >
            {reference.value}
          </button>
        ))}
      </div>
      <div className="mt-3 border-t border-[#dbeafe] pt-3">
        <div className="text-xs font-semibold text-[#344054]">Direct upstream data</div>
        {upstream.length === 0 ? (
          <p className="mt-1 text-xs leading-5 text-[#667085]">Connect a predecessor step to make its output available here.</p>
        ) : (
          <ul className="mt-1 space-y-1 text-xs leading-5 text-[#667085]">
            {upstream.map((node) => (
              <li key={node.id}>
                <code className="rounded bg-white px-1 py-0.5 text-[#344054]">upstream.{node.id}</code>
                <span className="ml-1">{configuredNodeLabel(node)} output</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px] leading-4 text-[#667085]">
          Node-specific paths are shown for traceability. Use <code>{"{{node_id.field}}"}</code> for a connected node output, or <code>{"{{upstream}}"}</code> for the full upstream-output object.
        </p>
      </div>
    </section>
  );
}
