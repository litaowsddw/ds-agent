/** Agent 相关类型定义。 */

/** Agent 类型枚举 - 对应 Supervisor / SubAgent 架构 */
export type AgentKind = "SUPERVISOR" | "USER_SUB" | "SYSTEM_SKILL" | "SYSTEM_RAG" | "SYSTEM_TOOL";

/** Agent 实体 */
export interface Agent {
  agent_id: string;
  org_id: string;
  team_id: string | null;
  name: string;
  description: string;
  /** Agent 类型，v0.1 仅默认 USER_SUB */
  kind?: AgentKind;
  /** Agent 所属 Workspace */
  workspace_id?: string;
  /** 模型供应商 key */
  model_provider?: string;
  /** 模型名称 */
  model_name?: string;
  /** 系统提示词 */
  system_prompt?: string;
  /** 采样温度 */
  temperature?: number | null;
  /** 最大输出 tokens */
  max_tokens?: number | null;
  /** 默认 Workflow，空值表示自主模式 */
  default_workflow_id?: string | null;
  created_by: string;
  created_at?: string;
}

/** Agent 创建请求 */
export interface CreateAgentRequest {
  actor_user_id: string;
  org_id: string;
  team_id?: string;
  name: string;
  description: string;
  kind?: AgentKind;
  model_provider?: string;
  model_name?: string;
  system_prompt?: string;
  temperature?: number | null;
  max_tokens?: number | null;
  default_workflow_id?: string | null;
}

/** Workspace 文件类型 */
export type WorkspaceFileKind = "AGENTS.md" | "SOUL.md" | "TOOLS.md" | "MEMORY.md";

/** Agent Workspace */
export interface AgentWorkspace {
  workspace_id: string;
  org_id: string;
  agent_id: string;
  files: Record<WorkspaceFileKind, string>;
  updated_by: string;
  updated_at?: string;
}

/** Workspace 状态 - 前端维护 */
export interface WorkspaceState {
  userId: string;
  orgId: string;
  teamId: string;
  email: string;
}
