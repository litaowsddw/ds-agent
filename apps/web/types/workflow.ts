/** Workflow 相关类型定义。 */

import type { Node, Edge } from "@xyflow/react";

/** Workflow 实体 */
export interface WorkflowItem {
  workflow_id: string;
  agent_id: string;
  name: string;
  description: string;
  draft_definition: WorkflowDefinition;
  published_version_id: string | null;
}

/** Workflow 版本 */
export interface WorkflowVersion {
  version_id: string;
  version_number: number;
}

/** Workflow 运行 */
export interface WorkflowRun {
  run_id: string;
  workflow_id: string;
  version_id: string;
  agent_id: string;
  status: string;
  output_data: Record<string, unknown>;
  error_message: string;
}

/** 节点运行日志 */
export interface NodeRun {
  node_run_id: string;
  node_id: string;
  node_type: string;
  status: string;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  error_message: string;
  elapsed_ms: number;
}

/** Workflow DSL 定义 */
export interface WorkflowDefinition {
  version: string;
  nodes: WorkflowNodeConfig[];
  edges: WorkflowEdgeConfig[];
}

/** Workflow 节点配置 */
export interface WorkflowNodeConfig {
  id: string;
  type: string;
  config: Record<string, unknown>;
}

/** Workflow 边配置 */
export interface WorkflowEdgeConfig {
  source: string;
  target: string;
}

/** LLM 节点表单状态 */
export interface LLMNodeForm {
  systemPrompt: string;
  prompt: string;
  temperature: string;
}

/** RAG 节点表单状态 */
export interface RAGNodeForm {
  queryTemplate: string;
  limit: string;
}

/** Tool 节点表单状态 */
export interface ToolNodeForm {
  toolId: string;
  arguments: string;
}

/** 自定义 React Flow 节点数据 */
export interface CustomNodeData extends Record<string, unknown> {
  label: string;
  icon?: string;
  description?: string;
  selected?: boolean;
}

/** 自定义节点类型常量 */
export const CUSTOM_NODE_TYPES = {
  LLM: "llm",
  RAG: "rag",
  TOOL: "tool",
  START: "start",
  END: "end",
} as const;

export type CustomNodeType = (typeof CUSTOM_NODE_TYPES)[keyof typeof CUSTOM_NODE_TYPES];

/** Workflow 创建请求 */
export interface CreateWorkflowRequest {
  actor_user_id: string;
  agent_id: string;
  name: string;
  description: string;
  draft_definition: WorkflowDefinition;
}
