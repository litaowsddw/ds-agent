/** AgentFlow API 客户端。

统一管理后端 API 调用，包含 JWT 认证、错误处理和类型安全。
 */

import type { ApiErrorPayload } from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// ── JWT Token 存储 ──

const TOKEN_KEY = "agentflow_access_token";
const TOKEN_ORG_KEY = "agentflow_current_org_id";

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

// ── API 请求 ──

/** 通用 API 请求函数（自动注入 JWT Token） */
export async function apiRequest<T>(
  path: string,
  options: { method?: string; body?: object } = {}
): Promise<T> {
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

export { API_BASE_URL };
