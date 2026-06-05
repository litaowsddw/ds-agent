/** Runtime 相关类型定义。 */

/** Skill 实体 */
export interface Skill {
  skill_id: string;
  name: string;
  description: string;
  scope: string;
}

/** Skill 使用评价 */
export interface SkillEvaluation {
  evaluation_id: string;
  org_id: string;
  agent_id: string;
  skill_id: string;
  session_id: string | null;
  user_input: string;
  assistant_output: string;
  status: string;
  score: number | null;
  failure_reason: string;
  improvement_suggestion: string;
  proposed_skill_patch: string;
  applied: boolean;
  created_by: string;
  created_at: string;
}

/** MCP Server */
export interface MCPServer {
  server_id: string;
  name: string;
  transport: string;
  url: string;
}

/** MCP Tool */
export interface MCPTool {
  tool_id: string;
  name: string;
  description: string;
  risk_level: string;
}

/** Memory 条目 */
export interface MemoryItem {
  memory_id: string;
  memory_type: string;
  summary: string;
  confidence: number;
}

/** Session 条目 */
export interface SessionItem {
  session_id: string;
  status: string;
  compact_summary: string;
}

/** Context Bundle */
export interface ContextBundle {
  total_estimated_tokens: number;
  need_compaction: boolean;
  sections: Array<{ name: string; content: string; estimated_tokens: number }>;
}

/** 模型供应商 */
export interface ModelProvider {
  provider_id: string;
  provider_key: string;
  display_name: string;
  base_url: string;
  api_key_masked: string;
  models: string[];
  default_model: string;
  is_enabled: boolean;
}

/** LLM 调用日志 */
export interface LLMCallLog {
  call_id: string;
  provider: string;
  model: string;
  status: string;
  prefix_hash: string;
}

/** 后台 Agent */
export interface BackgroundAgentItem {
  config_id: string;
  org_id: string;
  agent_type: string;
  enabled: boolean;
  interval_seconds: number;
  status: string;
}

/** Skill 创建请求 */
export interface CreateSkillRequest {
  actor_user_id: string;
  org_id: string;
  scope: string;
  team_id?: string;
  agent_id?: string;
  content: string;
}

/** MCP 创建请求 */
export interface CreateMCPServerRequest {
  actor_user_id: string;
  org_id: string;
  name: string;
  transport: string;
  url: string;
}

/** Memory 创建请求 */
export interface CreateMemoryRequest {
  actor_user_id: string;
  agent_id: string;
  memory_type: string;
  content: string;
  summary: string;
  confidence: number;
  source: string;
}

/** Model Provider 创建请求 */
export interface CreateModelProviderRequest {
  actor_user_id: string;
  org_id: string;
  provider_key: string;
  display_name: string;
  base_url: string;
  api_key: string;
  models: string[];
  default_model: string;
}
