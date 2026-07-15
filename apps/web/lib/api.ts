/** AgentFlow API 客户端。

统一管理后端 API 调用，包含 JWT 认证、错误处理和类型安全。
 */

import type { ApiErrorPayload } from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:18000";

// ── JWT Token 存储 ──

const TOKEN_KEY = "agentflow_access_token";
const TOKEN_ORG_KEY = "agentflow_current_org_id";
let organizationTokenSync: Promise<void> | null = null;

/** 获取存储的 JWT Token */
export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/** 存储 JWT Token */
export function setAccessToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

/** 清除 JWT Token */
export function clearAccessToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_ORG_KEY);
}

/** 清除当前组织上下文，保留登录 Token。 */
export function clearCurrentOrgId(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_ORG_KEY);
}

/** 获取当前组织 ID */
export function getCurrentOrgId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_ORG_KEY);
}

/** 设置当前组织 ID */
export function setCurrentOrgId(orgId: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_ORG_KEY, orgId);
}

/** 检查是否已登录 */
export function isAuthenticated(): boolean {
  return !!getAccessToken();
}

/**
 * Keep the workspace organization and the organization in the JWT aligned.
 * Gateway and metering routes deliberately read the signed JWT claim instead
 * of trusting a browser-provided organization header.
 */
async function synchronizeOrganizationToken(path: string): Promise<void> {
  if (path === "/health" || path.startsWith("/identity/users/switch-org")) return;

  const token = getAccessToken();
  const orgId = getCurrentOrgId();
  if (!token || !orgId || jwtOrganizationId(token) === orgId) return;

  if (!organizationTokenSync) {
    organizationTokenSync = (async () => {
      const response = await fetch(
        `${API_BASE_URL}/identity/users/switch-org?org_id=${encodeURIComponent(orgId)}`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      if (!response.ok) return;
      const result = (await response.json()) as { access_token?: string };
      if (result.access_token) setAccessToken(result.access_token);
    })().finally(() => {
      organizationTokenSync = null;
    });
  }

  await organizationTokenSync;
}

function jwtOrganizationId(token: string): string | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="))) as {
      org_id?: string;
    };
    return decoded.org_id || null;
  } catch {
    return null;
  }
}

// ── API 请求 ──

/** 通用 API 请求函数（自动注入 JWT Token） */
export async function apiRequest<T>(
  path: string,
  options: { method?: string; body?: object } = {}
): Promise<T> {
  await synchronizeOrganizationToken(path);
  const headers: Record<string, string> = {};

  // 自动注入 JWT Token
  const token = getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // 注入当前组织上下文
  const orgId = getCurrentOrgId();
  if (orgId) {
    headers["X-Current-Org-Id"] = orgId;
  }

  if (options.body) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  // 401 自动清除 Token
  if (response.status === 401) {
    clearAccessToken();
    throw new Error("登录已过期，请重新登录");
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      detail = formatApiErrorDetail(payload.detail) ?? detail;
    } catch {
      detail = response.statusText;
    }
    throw new Error(`请求失败：${detail}`);
  }

  return (await response.json()) as T;
}

/** FormData 上传请求 */
export async function apiFormRequest<T>(path: string, formData: FormData): Promise<T> {
  const headers: Record<string, string> = {};

  const token = getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      detail = formatApiErrorDetail(payload.detail) ?? detail;
    } catch {
      detail = response.statusText;
    }
    throw new Error(`请求失败：${detail}`);
  }

  return (await response.json()) as T;
}

/** 格式化 API 错误详情 */
function formatApiErrorDetail(detail: ApiErrorPayload["detail"]): string | undefined {
  if (!detail) return undefined;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg ?? JSON.stringify(item)).join("；");
  return detail.msg ?? JSON.stringify(detail);
}

// ── 认证 API ──

/** 登录请求参数 */
export interface LoginParams {
  email: string;
  password: string;
}

/** 登录响应 */
export interface LoginResponse {
  user: {
    user_id: string;
    email: string;
    display_name: string;
  };
  token: {
    access_token: string;
    token_type: string;
  };
  default_org_id: string | null;
  default_role: string | null;
}

/** 用户登录 */
export async function login(params: LoginParams): Promise<LoginResponse> {
  const result = await apiRequest<LoginResponse>("/identity/users/login", {
    method: "POST",
    body: params,
  });
  // 存储 Token
  setAccessToken(result.token.access_token);
  if (result.default_org_id) {
    setCurrentOrgId(result.default_org_id);
  }
  return result;
}

/** 用户登出 */
export function logout(): void {
  clearAccessToken();
}

/** 切换组织 */
export async function switchOrganization(orgId: string): Promise<void> {
  const result = await apiRequest<{ access_token: string; token_type: string }>(
    `/identity/users/switch-org?org_id=${orgId}`,
    { method: "POST" }
  );
  setAccessToken(result.access_token);
  setCurrentOrgId(orgId);
}

/** 健康检查 */
export async function checkHealth(): Promise<{ status: string }> {
  return apiRequest<{ status: string }>("/health");
}

export type UsageGroupBy = "api" | "provider" | "model" | "agent" | "workflow" | "source";
export type UsageGranularity = "hour" | "day";

/** Filters accepted by the organization-scoped metering endpoints. */
export interface UsageQueryFilters {
  from?: string;
  to?: string;
  source?: string;
  api_name?: string;
  provider_key?: string;
  model?: string;
  agent_id?: string;
  workflow_id?: string;
  workflow_run_id?: string;
  group_by?: UsageGroupBy;
  granularity?: UsageGranularity;
  offset?: number;
  limit?: number;
}

export interface UsageAggregate {
  bucket_start?: string | null;
  api_name?: string | null;
  provider_key?: string | null;
  model?: string | null;
  agent_id?: string | null;
  workflow_id?: string | null;
  source?: string | null;
  call_count: number;
  unknown_usage_calls: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  reasoning_tokens?: number | null;
  cache_read_input_tokens?: number | null;
  cache_write_input_tokens?: number | null;
  /** Reserved for future priced responses; omitted means no estimate is available. */
  estimated_total_cost?: number | null;
  currency?: string | null;
}

export interface UsageSummaryResponse {
  org_id: string;
  group_by: UsageGroupBy;
  granularity: UsageGranularity;
  created_at_from: string;
  created_at_to: string;
  groups: UsageAggregate[];
}

export interface UsageEvent {
  event_id: string;
  gateway_call_id: string;
  created_at: string;
  source: string;
  api_name: string;
  provider_key: string;
  model: string;
  agent_id?: string | null;
  workflow_id?: string | null;
  workflow_run_id?: string | null;
  dispatch_status: string;
  usage_status: string;
  cache_usage_status: string;
  prefix_cache_status?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  cache_read_input_tokens?: number | null;
  latency_ms?: number | null;
}

export interface UsageEventsResponse {
  org_id: string;
  created_at_from: string;
  created_at_to: string;
  events: UsageEvent[];
  offset: number;
  limit: number;
  has_more: boolean;
}

function usageQuery(filters: UsageQueryFilters): string {
  const params = new URLSearchParams();
  const entries: Array<[string, string | number | undefined]> = [
    ["from", filters.from],
    ["to", filters.to],
    ["source", filters.source],
    ["api", filters.api_name],
    ["provider", filters.provider_key],
    ["model", filters.model],
    ["agent", filters.agent_id],
    ["workflow", filters.workflow_id],
    ["workflow_run", filters.workflow_run_id],
    ["group_by", filters.group_by],
    ["granularity", filters.granularity],
    ["offset", filters.offset],
    ["limit", filters.limit],
  ];
  for (const [key, value] of entries) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

/** Read redacted, tenant-authorized aggregate provider usage. */
export function getUsageSummary(filters: UsageQueryFilters = {}): Promise<UsageSummaryResponse> {
  return apiRequest<UsageSummaryResponse>(`/metering/usage/summary${usageQuery(filters)}`);
}

/** Read redacted usage-event dimensions only; no prompts or credentials are returned. */
export function getUsageEvents(filters: UsageQueryFilters = {}): Promise<UsageEventsResponse> {
  return apiRequest<UsageEventsResponse>(`/metering/usage/events${usageQuery(filters)}`);
}

export { API_BASE_URL };
