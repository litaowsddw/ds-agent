/** 前端常量定义。 */

/** 侧边栏导航项 */
export const NAV_ITEMS = [
  { key: "agents", label: "Agents", icon: "Bot", href: "/agents" },
  { key: "chat", label: "Chat", icon: "MessageSquare", href: "/chat" },
  { key: "workflow", label: "Workflow", icon: "Workflow", href: "/workflows" },
  { key: "runtime", label: "Runtime", icon: "Brain", href: "/runtime" },
  { key: "knowledge", label: "Knowledge", icon: "Database", href: "/knowledge" },
  { key: "runs", label: "Runs", icon: "Activity", href: "/runs" },
] as const;

/** 节点面板项 - 画布中可添加的节点类型 */
export const NODE_PALETTE = [
  { label: "LLM", description: "模型推理", icon: "Bot", type: "llm" },
  { label: "RAG", description: "知识检索", icon: "Database", type: "rag" },
  { label: "Tool", description: "工具调用", icon: "ShieldCheck", type: "tool" },
] as const;

/** 默认画布节点 */
export const INITIAL_NODES = [
  { id: "start", type: "start", position: { x: 40, y: 220 }, data: { label: "Start" } },
  { id: "llm", type: "llm", position: { x: 300, y: 220 }, data: { label: "LLM" } },
  { id: "end", type: "end", position: { x: 560, y: 220 }, data: { label: "End" } },
];

/** 默认画布边 */
export const INITIAL_EDGES = [
  { id: "start-llm", source: "start", target: "llm" },
  { id: "llm-end", source: "llm", target: "end" },
];

/** Toast 自动消失时间 (ms) */
export const TOAST_DURATION = 4000;

/** Tailwind 自定义颜色 token */
export const COLORS = {
  canvas: "#f7f8fa",
  panel: "#ffffff",
  ink: "#172033",
  muted: "#667085",
  line: "#dfe4ee",
  accent: "#1677ff",
  accentHover: "#255dc7",
  accentLight: "#eef4ff",
  success: "#027a48",
  successBg: "#ecfdf3",
  warning: "#c2410c",
  warningBg: "#fff7ed",
  error: "#b42318",
  errorBg: "#fef2f2",
} as const;
