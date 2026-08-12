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
  /** Optional deterministic guardrails for one workflow run, never a billing policy. */
  execution_limits?: WorkflowExecutionLimits;
}

export interface WorkflowExecutionLimits {
  max_steps?: number;
  max_llm_calls?: number;
}

/**
 * A curated starting point for a new workflow.  Templates deliberately carry
 * only workflow DSL: they never include tenant-specific provider credentials,
 * knowledge-base IDs, or tool authorisations.
 */
export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  suggestedName: string;
  setup: string[];
  definition: WorkflowDefinition;
}

export interface WorkflowNodeConfig {
  id: string;
  type: string;
  config: Record<string, unknown>;
  /** Canvas coordinates. Persisted as editor metadata; the backend ignores it. */
  position?: { x: number; y: number };
}

export interface WorkflowEdgeConfig {
  source: string;
  target: string;
  /** Condition nodes route through one explicitly named output branch. */
  branch?: "true" | "false";
}

export interface CustomNodeData extends Record<string, unknown> {
  label: string;
  description?: string;
  capability?: "executable" | "schema";
  config?: Record<string, unknown>;
  /** Latest run status for this node, mapped from node runs. */
  runStatus?: string;
  /** Opens the quick-add menu anchored to this node (Dify-style "+" affordance). */
  onQuickAdd?: (nodeId: string, branch?: "true" | "false") => void;
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
