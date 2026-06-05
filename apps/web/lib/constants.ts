/** Frontend constants. */

export const NAV_ITEMS = [
  { key: "agents", label: "Agents", icon: "Bot", href: "/agents" },
  { key: "chat", label: "Chat", icon: "MessageSquare", href: "/chat" },
  { key: "workflow", label: "Workflow", icon: "Workflow", href: "/workflows" },
  { key: "runtime", label: "Runtime", icon: "Brain", href: "/runtime" },
  { key: "knowledge", label: "Knowledge", icon: "Database", href: "/knowledge" },
  { key: "runs", label: "Runs", icon: "Activity", href: "/runs" },
] as const;

export type WorkflowNodeCapability = "executable" | "schema";

export interface WorkflowPaletteItem {
  type: string;
  label: string;
  description: string;
  group: "Core" | "AI" | "Knowledge" | "Tools" | "Logic" | "Human" | "Data";
  icon: string;
  capability: WorkflowNodeCapability;
}

export const NODE_PALETTE: WorkflowPaletteItem[] = [
  {
    type: "llm",
    label: "LLM",
    description: "Model call through a configured provider",
    group: "AI",
    icon: "Bot",
    capability: "executable",
  },
  {
    type: "rag",
    label: "Knowledge Retrieval",
    description: "Search a knowledge base with vector retrieval",
    group: "Knowledge",
    icon: "Database",
    capability: "executable",
  },
  {
    type: "tool",
    label: "Tool",
    description: "Use an authorized MCP tool plan",
    group: "Tools",
    icon: "ShieldCheck",
    capability: "executable",
  },
  {
    type: "condition",
    label: "Condition",
    description: "Branch by expression or upstream value",
    group: "Logic",
    icon: "GitBranch",
    capability: "schema",
  },
  {
    type: "http",
    label: "HTTP Request",
    description: "Call an external HTTP endpoint",
    group: "Tools",
    icon: "Globe",
    capability: "schema",
  },
  {
    type: "code",
    label: "Code",
    description: "Transform data with sandboxed code",
    group: "Logic",
    icon: "Code2",
    capability: "schema",
  },
  {
    type: "variable",
    label: "Variable",
    description: "Assign workflow variables",
    group: "Data",
    icon: "Braces",
    capability: "schema",
  },
  {
    type: "template",
    label: "Template",
    description: "Render text from upstream context",
    group: "Data",
    icon: "TextCursorInput",
    capability: "schema",
  },
  {
    type: "human",
    label: "Human Approval",
    description: "Pause for manual review",
    group: "Human",
    icon: "UserCheck",
    capability: "schema",
  },
];

export const INITIAL_NODES = [
  {
    id: "start",
    type: "start",
    position: { x: 80, y: 260 },
    data: {
      label: "Start",
      description: "Workflow input",
      capability: "executable",
      config: {},
    },
  },
  {
    id: "llm",
    type: "llm",
    position: { x: 380, y: 260 },
    data: {
      label: "LLM",
      description: "Model call",
      capability: "executable",
      config: {
        provider: "",
        model: "",
        system_prompt: "",
        prompt: "",
        temperature: 0,
        max_tokens: 512,
      },
    },
  },
  {
    id: "end",
    type: "end",
    position: { x: 700, y: 260 },
    data: {
      label: "End",
      description: "Workflow result",
      capability: "executable",
      config: {},
    },
  },
];

export const INITIAL_EDGES = [
  { id: "start-llm", source: "start", target: "llm" },
  { id: "llm-end", source: "llm", target: "end" },
];

export const TOAST_DURATION = 4000;

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
