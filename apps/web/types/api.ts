/** API 通用类型定义。 */

/** API 错误响应 */
export interface ApiErrorPayload {
  detail?: string | { msg?: string } | Array<{ msg?: string }>;
}

/** Toast 类型 */
export type ToastKind = "info" | "success" | "error";

/** API 状态 */
export type ApiStatus = "checking" | "online" | "offline";

/** 侧边栏导航项 */
export interface NavItem {
  key: string;
  label: string;
  icon: string;
  href: string;
}

/** 节点面板项 */
export interface NodePaletteItem {
  label: string;
  description: string;
  icon: string;
  type: string;
}
