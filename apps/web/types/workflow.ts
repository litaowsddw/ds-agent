/** Workflow types. */

export interface WorkflowItem {
  workflow_id: string;
  agent_id: string;
  name: string;
  description: string;
  draft_definition: WorkflowDefinition;
  published_version_id: string | null;
}

export interface WorkflowVersion {
  version_id: string;
  workflow_id: string;
  org_id: string;
  version_number: number;
  definition: WorkflowDefinition;
  release_note: string;
  created_by: string;
  created_at: string;
}

export interface WorkflowValidationResult {
  valid: boolean;
  errors: string[];
}

export interface WorkflowRun {
  run_id: string;
  workflow_id: string;
  version_id: string;
  agent_id: string;
  input_data: Record<string, unknown>;
  status: string;
  output_data: Record<string, unknown>;
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string | null;
}

export interface NodeRun {
  node_run_id: string;
  node_id: string;
  node_type: string;
  status: string;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  error_message: string;
  elapsed_ms: number;
  sequence?: number;
}

export interface WorkflowDefinition {
  version: string;
  nodes: WorkflowNodeConfig[];
  edges: WorkflowEdgeConfig[];
}

export interface WorkflowNodeConfig {
  id: string;
  type: string;
  config: Record<string, unknown>;
}

export interface WorkflowEdgeConfig {
  source: string;
  target: string;
}

export interface CustomNodeData extends Record<string, unknown> {
  label: string;
  description?: string;
  capability?: "executable" | "schema";
  config?: Record<string, unknown>;
}

export const CUSTOM_NODE_TYPES = {
  START: "start",
  END: "end",
  LLM: "llm",
  RAG: "rag",
  TOOL: "tool",
  CONDITION: "condition",
  HTTP: "http",
  CODE: "code",
  VARIABLE: "variable",
  TEMPLATE: "template",
  HUMAN: "human",
} as const;

export type CustomNodeType = (typeof CUSTOM_NODE_TYPES)[keyof typeof CUSTOM_NODE_TYPES];

export interface CreateWorkflowRequest {
  actor_user_id: string;
  agent_id: string;
  name: string;
  description: string;
  draft_definition: WorkflowDefinition;
}
