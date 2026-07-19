import { create } from "zustand";
import { API_BASE_URL, apiRequest, getAccessToken, getCurrentOrgId } from "@/lib/api";
import { wsManager } from "@/lib/websocket";

export interface Message {
  message_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sequence: number;
  meta_info?: Record<string, unknown>;
  created_at: string;
}

export interface ChatSession {
  session_id: string;
  status: string;
  compact_summary: string;
  created_at: string;
  updated_at: string;
}

export interface ChatTraceEvent {
  id: string;
  event: string;
  node?: string;
  label?: string;
  status: "running" | "succeeded" | "failed" | "info";
  text?: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface ActualContextUsage {
  inputTokens: number | null;
  outputTokens: number;
  contextTokens: number | null;
  outputTokenStatus: "official_tokenizer" | "characters_divided_by_4" | "provider_final" | "unavailable";
  cacheReadInputTokens: number | null;
  tokenLimit: number;
  usageStatus: "provider_final" | "unavailable";
  preflightInputTokens: number | null;
  stablePrefixTokens: number | null;
  tokenizerStatus: "official_tokenizer" | "official_total_only" | "characters_divided_by_4";
  tokenizer: string | null;
  promptBreakdown: Array<{ key: string; label: string; tokens: number }>;
  calibrationStatus: CalibrationStatus;
  activeWorkflowNodeId: string | null;
}

export type CalibrationStatus =
  | "estimated"
  | "partially_calibrated"
  | "provider_final"
  | "unavailable";

type UsageScope = "chat" | "skill_create" | "workflow";
type UsagePhase = "preflight" | "estimated" | "provider_final" | "unavailable";

interface UsageCallState {
  key: string;
  scope: UsageScope;
  workflowNodeId: string | null;
  estimatedInputTokens: number | null;
  estimatedOutputTokens: number;
  finalInputTokens: number | null;
  finalOutputTokens: number | null;
  tokenLimit: number;
  phase: UsagePhase;
  hasProgress: boolean;
  cacheReadInputTokens: number | null;
  stablePrefixTokens: number | null;
  tokenizerStatus: "official_tokenizer" | "official_total_only" | "characters_divided_by_4";
  tokenizer: string | null;
  promptBreakdown: Array<{ key: string; label: string; tokens: number }>;
}

export type ChatExecutionMode = "autonomous" | "workflow";

export interface SendMessageOptions {
  executionMode?: ChatExecutionMode;
  workflowId?: string;
}

export interface FailedSendSnapshot {
  agentId: string;
  orgId: string;
  actorUserId?: string;
  message: string;
  options: SendMessageOptions;
}

interface ChatState {
  sessionId: string | null;
  sessions: ChatSession[];
  messages: Message[];
  traceEvents: ChatTraceEvent[];
  isGenerating: boolean;
  agentId: string | null;
  intent: string;
  subtaskCount: number;
  failedSendSnapshot: FailedSendSnapshot | null;
  actualContextUsage: ActualContextUsage | null;
  usageCalls: Record<string, UsageCallState>;

  sendMessage: (
    agentId: string,
    orgId: string,
    message: string,
    actorUserId?: string,
    options?: SendMessageOptions
  ) => Promise<void>;
  retryLastMessage: () => Promise<void>;
  loadLatestSession: (agentId: string, actorUserId: string) => Promise<void>;
  loadSessionHistory: (agentId: string, actorUserId: string) => Promise<void>;
  loadMessages: (sessionId: string) => Promise<void>;
  clearSession: () => void;
  subscribeMessages: () => () => void;
}

let activeChatGeneration = 0;

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: null,
  sessions: [],
  messages: [],
  traceEvents: [],
  isGenerating: false,
  agentId: null,
  intent: "",
  subtaskCount: 0,
  failedSendSnapshot: null,
  actualContextUsage: null,
  usageCalls: {},

  sendMessage: async (agentId, orgId, message, actorUserId, options) => {
    const generation = ++activeChatGeneration;
    const isActive = () => generation === activeChatGeneration && get().agentId === agentId;
    const snapshot: FailedSendSnapshot = {
      agentId,
      orgId,
      actorUserId,
      message,
      options: {
        executionMode: options?.executionMode ?? "autonomous",
        workflowId: options?.workflowId,
      },
    };
    let streamFailed = false;
    set({
      isGenerating: true,
      agentId,
      traceEvents: [],
      failedSendSnapshot: null,
      actualContextUsage: null,
      usageCalls: {},
    });

    const userMsg: Message = {
      message_id: `temp_${Date.now()}`,
      role: "user",
      content: message,
      sequence: get().messages.length,
      created_at: new Date().toISOString(),
    };
    const assistantId = `resp_${Date.now()}`;
    const assistantMsg: Message = {
      message_id: assistantId,
      role: "assistant",
      content: "",
      sequence: get().messages.length + 1,
      created_at: new Date().toISOString(),
    };
    set((state) => ({ messages: [...state.messages, userMsg, assistantMsg] }));

    try {
      await streamChat({
        agentId,
        orgId,
        actorUserId,
        message,
        sessionId: get().sessionId,
        executionMode: options?.executionMode ?? "autonomous",
        workflowId: options?.workflowId,
        onEvent: (event, data) => {
          if (!isActive()) return;
          if (event === "token") {
            const text = String(data.text ?? "");
            set((state) => ({
              messages: state.messages.map((item) =>
                item.message_id === assistantId ? { ...item, content: item.content + text } : item
              ),
            }));
          }

          if (event === "run_finished") {
            const finishedSessionId = String(data.session_id ?? get().sessionId ?? "");
            set((state) => ({
              sessionId: finishedSessionId,
              isGenerating: false,
              sessions: finishedSessionId && !state.sessions.some((item) => item.session_id === finishedSessionId)
                ? [
                    {
                      session_id: finishedSessionId,
                      status: "idle",
                      compact_summary: "",
                      created_at: new Date().toISOString(),
                      updated_at: new Date().toISOString(),
                    },
                    ...state.sessions,
                  ]
                : state.sessions,
            }));
          }

          if (event === "context_preflight" || event === "context_progress" || event === "context_usage") {
            set((state) => {
              const usageKey = typeof data.usage_key === "string" && data.usage_key
                ? data.usage_key
                : "chat:default";
              const previousCall = state.usageCalls[usageKey];
              const phase = getUsagePhase(event, data);
              const inputTokens = typeof data.input_tokens === "number" ? data.input_tokens : null;
              const outputTokens = typeof data.output_tokens === "number" ? data.output_tokens : null;
              const usageCall: UsageCallState = {
                key: usageKey,
                scope: getUsageScope(data.usage_scope, previousCall?.scope),
                workflowNodeId: typeof data.workflow_node_id === "string"
                  ? data.workflow_node_id
                  : previousCall?.workflowNodeId ?? null,
                estimatedInputTokens: phase === "provider_final" || phase === "unavailable"
                  ? previousCall?.estimatedInputTokens ?? null
                  : inputTokens ?? previousCall?.estimatedInputTokens ?? null,
                estimatedOutputTokens: phase === "provider_final"
                  ? previousCall?.estimatedOutputTokens ?? 0
                  : outputTokens ?? previousCall?.estimatedOutputTokens ?? 0,
                finalInputTokens: phase === "provider_final"
                  ? inputTokens
                  : previousCall?.finalInputTokens ?? null,
                finalOutputTokens: phase === "provider_final"
                  ? outputTokens
                  : previousCall?.finalOutputTokens ?? null,
                tokenLimit: typeof data.token_limit === "number"
                  ? data.token_limit
                  : previousCall?.tokenLimit ?? 2400,
                phase,
                hasProgress: event === "context_progress" || previousCall?.hasProgress === true,
                cacheReadInputTokens: typeof data.cache_read_input_tokens === "number"
                  ? data.cache_read_input_tokens
                  : previousCall?.cacheReadInputTokens ?? null,
                stablePrefixTokens: typeof data.stable_prefix_tokens === "number"
                  ? data.stable_prefix_tokens
                  : previousCall?.stablePrefixTokens ?? null,
                tokenizerStatus: getTokenizerStatus(data.tokenizer_status, previousCall?.tokenizerStatus),
                tokenizer: typeof data.tokenizer === "string" ? data.tokenizer : previousCall?.tokenizer ?? null,
                promptBreakdown: getPromptBreakdown(data.prompt_breakdown) ?? previousCall?.promptBreakdown ?? [],
              };
              const usageCalls = { ...state.usageCalls };
              if (event === "context_progress" && previousCall) delete usageCalls[usageKey];
              usageCalls[usageKey] = usageCall;
              return { usageCalls, actualContextUsage: aggregateUsage(usageCalls) };
            });
          }

          if (event === "error") {
            streamFailed = true;
            const detail = typeof data.error === "string" ? data.error.trim() : "";
            const errorText = detail ? `对话失败：${detail}` : "对话失败";
            set((state) => ({
              messages: state.messages.map((item) =>
                item.message_id === assistantId ? { ...item, role: "system", content: errorText } : item
              ),
              isGenerating: false,
              failedSendSnapshot: snapshot,
            }));
          }

          appendTraceEvent(set, event, data);
        },
      });
      if (!isActive()) return;
      set({ isGenerating: false, failedSendSnapshot: streamFailed ? snapshot : null });
    } catch (error) {
      if (!isActive()) return;
      const detail = error instanceof Error ? error.message.trim() : "";
      const errorText = detail.startsWith("请求失败")
        ? detail
        : detail
          ? `消息发送失败：${detail}`
          : "消息发送失败";
      set((state) => ({
        messages: state.messages.map((item) =>
          item.message_id === assistantId ? { ...item, role: "system", content: errorText } : item
        ),
        isGenerating: false,
        failedSendSnapshot: snapshot,
      }));
    }
  },

  retryLastMessage: async () => {
    const snapshot = get().failedSendSnapshot;
    if (!snapshot || get().isGenerating) return;
    await get().sendMessage(
      snapshot.agentId,
      snapshot.orgId,
      snapshot.message,
      snapshot.actorUserId,
      { ...snapshot.options }
    );
  },

  loadLatestSession: async (agentId, actorUserId) => {
    if (!agentId || !actorUserId) return;
    const generation = ++activeChatGeneration;
    set({
      agentId,
      sessionId: null,
      sessions: [],
      messages: [],
      traceEvents: [],
      failedSendSnapshot: null,
      isGenerating: false,
      intent: "",
      subtaskCount: 0,
      actualContextUsage: null,
      usageCalls: {},
    });
    try {
      const result = await apiRequest<{ session_id: string | null; messages: Message[] }>(
        `/chat/agents/${agentId}/latest-session?actor_user_id=${actorUserId}`
      );
      if (generation !== activeChatGeneration || get().agentId !== agentId) return;
      set({
        agentId,
        sessionId: result.session_id,
        messages: result.messages || [],
        traceEvents: [],
      });
    } catch {
      if (generation !== activeChatGeneration || get().agentId !== agentId) return;
      set({ agentId, sessionId: null, messages: [], traceEvents: [] });
    }
  },

  loadSessionHistory: async (agentId, actorUserId) => {
    if (!agentId || !actorUserId) return;
    try {
      const sessions = await apiRequest<ChatSession[]>(
        `/sessions?agent_id=${encodeURIComponent(agentId)}&actor_user_id=${encodeURIComponent(actorUserId)}`
      );
      if (get().agentId !== agentId) return;
      set({ sessions: [...sessions].sort((left, right) => right.updated_at.localeCompare(left.updated_at)) });
    } catch {
      if (get().agentId === agentId) set({ sessions: [] });
    }
  },

  loadMessages: async (sessionId) => {
    try {
      const result = await apiRequest<{ messages: Message[] }>(`/chat/sessions/${sessionId}/messages`);
      set({ sessionId, messages: result.messages || [], actualContextUsage: null, usageCalls: {} });
    } catch {
      // Keep the current local messages when history loading fails.
    }
  },

  clearSession: () => {
    activeChatGeneration += 1;
    set({
      sessionId: null,
      sessions: [],
      messages: [],
      traceEvents: [],
      intent: "",
      subtaskCount: 0,
      actualContextUsage: null,
      usageCalls: {},
      failedSendSnapshot: null,
      isGenerating: false,
    });
  },

  subscribeMessages: () => {
    return wsManager.on("chat_message", (_event, data) => {
      const msg = data as Message;
      set((state) => ({ messages: [...state.messages, msg] }));
    });
  },
}));

function getUsageScope(value: unknown, fallback: UsageScope | undefined): UsageScope {
  return value === "chat" || value === "skill_create" || value === "workflow"
    ? value
    : fallback ?? "chat";
}

function getUsagePhase(event: string, data: Record<string, unknown>): UsagePhase {
  if (
    data.usage_phase === "preflight" ||
    data.usage_phase === "estimated" ||
    data.usage_phase === "provider_final" ||
    data.usage_phase === "unavailable"
  ) {
    return data.usage_phase;
  }
  if (data.usage_status === "provider_final") return "provider_final";
  if (data.usage_status === "unavailable") return "unavailable";
  if (event === "context_preflight") return "preflight";
  if (event === "context_progress") return "estimated";
  return "unavailable";
}

function getTokenizerStatus(
  value: unknown,
  fallback: UsageCallState["tokenizerStatus"] | undefined
): UsageCallState["tokenizerStatus"] {
  return value === "official_tokenizer" || value === "official_total_only" || value === "characters_divided_by_4"
    ? value
    : fallback ?? "characters_divided_by_4";
}

function getPromptBreakdown(value: unknown): Array<{ key: string; label: string; tokens: number }> | null {
  if (!Array.isArray(value)) return null;
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const section = item as Record<string, unknown>;
    return typeof section.key === "string" && typeof section.label === "string" && typeof section.tokens === "number"
      ? [{ key: section.key, label: section.label, tokens: section.tokens }]
      : [];
  });
}

function aggregateUsage(calls: Record<string, UsageCallState>): ActualContextUsage {
  const entries = Object.values(calls);
  const isFinal = (entry: UsageCallState) => entry.phase === "provider_final";
  const inputTokens = entries.reduce<number | null>((total, entry) => {
    const value = isFinal(entry) ? entry.finalInputTokens : entry.estimatedInputTokens;
    return value === null || total === null ? null : total + value;
  }, 0);
  const outputTokens = entries.reduce(
    (total, entry) => total + (isFinal(entry)
      ? entry.finalOutputTokens ?? entry.estimatedOutputTokens
      : entry.estimatedOutputTokens),
    0,
  );
  const finalCount = entries.filter(isFinal).length;
  const calibrationStatus: CalibrationStatus =
    finalCount === entries.length && entries.length > 0 ? "provider_final" :
    finalCount > 0 ? "partially_calibrated" :
    entries.every((entry) => entry.phase === "unavailable") ? "unavailable" :
    "estimated";
  const activeWorkflow = [...entries].reverse().find(
    (entry) => entry.scope === "workflow" && entry.hasProgress && !isFinal(entry) && entry.phase !== "unavailable",
  );
  const cacheReadInputTokens = entries.length > 0 && entries.every((entry) => entry.cacheReadInputTokens !== null)
    ? entries.reduce((total, entry) => total + (entry.cacheReadInputTokens ?? 0), 0)
    : null;
  const lastEntry = entries.at(-1);

  return {
    inputTokens,
    outputTokens,
    contextTokens: inputTokens === null ? null : inputTokens + outputTokens,
    outputTokenStatus: calibrationStatus === "provider_final" ? "provider_final" : "characters_divided_by_4",
    cacheReadInputTokens,
    tokenLimit: lastEntry?.tokenLimit ?? 2400,
    usageStatus: calibrationStatus === "provider_final" ? "provider_final" : "unavailable",
    preflightInputTokens: inputTokens,
    stablePrefixTokens: lastEntry?.stablePrefixTokens ?? null,
    tokenizerStatus: lastEntry?.tokenizerStatus ?? "characters_divided_by_4",
    tokenizer: lastEntry?.tokenizer ?? null,
    promptBreakdown: entries.flatMap((entry) => entry.promptBreakdown.map((section) => ({
      ...section,
      key: `${entry.key}:${section.key}`,
    }))),
    calibrationStatus,
    activeWorkflowNodeId: activeWorkflow?.workflowNodeId ?? null,
  };
}

async function streamChat({
  agentId,
  orgId,
  actorUserId,
  message,
  sessionId,
  executionMode,
  workflowId,
  onEvent,
}: {
  agentId: string;
  orgId: string;
  actorUserId?: string;
  message: string;
  sessionId: string | null;
  executionMode: ChatExecutionMode;
  workflowId?: string;
  onEvent: (event: string, data: Record<string, unknown>) => void;
}) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const currentOrgId = getCurrentOrgId();
  if (currentOrgId) headers["X-Current-Org-Id"] = currentOrgId;

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      agent_id: agentId,
      message,
      session_id: sessionId,
      stream: true,
      execution_mode: executionMode,
      workflow_id: workflowId || null,
    }),
  });

  if (!response.ok || !response.body) {
    const detail = response.statusText.trim();
    throw new Error(detail ? `请求失败：${detail}` : "请求失败");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const parsed = parseSseFrame(frame);
      if (parsed) onEvent(parsed.event, parsed.data);
    }
  }
}

function parseSseFrame(frame: string): { event: string; data: Record<string, unknown> } | null {
  const lines = frame
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.trimEnd());
  const eventLine = lines.find((line) => line.startsWith("event:"));
  const dataLines = lines.filter((line) => line.startsWith("data:"));
  if (!eventLine || dataLines.length === 0) return null;
  try {
    return {
      event: eventLine.replace("event:", "").trim(),
      data: JSON.parse(dataLines.map((line) => line.replace("data:", "").trim()).join("\n")) as Record<string, unknown>,
    };
  } catch {
    return null;
  }
}

function appendTraceEvent(
  set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void,
  event: string,
  data: Record<string, unknown>
) {
  // High-frequency stream and context-meter events belong to the composer,
  // not the execution trace.  Keeping them out avoids hundreds of invisible
  // trace records and unnecessary scroll/render work on long responses.
  if (event === "token" || event === "context_preflight" || event === "context_progress" || event === "context_usage") {
    return;
  }
  const status =
    event === "node_started"
      ? "running"
      : event === "error"
        ? "failed"
        : event === "node_finished" || event === "run_finished" || event === "skill_created"
          ? "succeeded"
          : "info";
  set((state) => ({
    traceEvents: upsertTraceEvent(state.traceEvents, event, data, status),
  }));
}

function upsertTraceEvent(
  events: ChatTraceEvent[],
  event: string,
  data: Record<string, unknown>,
  status: ChatTraceEvent["status"]
): ChatTraceEvent[] {
  const node = typeof data.node === "string" ? data.node : undefined;
  const label = typeof data.label === "string" ? data.label : undefined;
  const nextEvent: ChatTraceEvent = {
    id: `${Date.now()}_${events.length}`,
    event,
    node,
    label,
    status,
    text: typeof data.text === "string" ? data.text : undefined,
    data,
    created_at: new Date().toISOString(),
  };

  if (event === "error") {
    return [
      ...events.map((item) => (item.status === "running" ? { ...item, status: "failed" as const } : item)),
      nextEvent,
    ];
  }

  if (event === "node_finished" && node) {
    const index = findLastIndex(events, (item) => item.node === node && item.event === "node_started");
    if (index >= 0) {
      return events.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              event,
              label: label || item.label,
              status,
              data: { ...item.data, ...data },
            }
          : item
      );
    }
  }

  if (event === "run_finished") {
    return events.map((item) => (item.status === "running" ? { ...item, status: "succeeded" } : item));
  }

  return [...events, nextEvent];
}

function findLastIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) return index;
  }
  return -1;
}

export interface EvolutionRecord {
  record_id: string;
  agent_id: string;
  action: string;
  skill_name: string;
  confidence: number;
  status: string;
  reasoning: string;
  created_at: string;
  applied_at: string;
}

interface EvolverState {
  history: EvolutionRecord[];
  pendingApprovals: EvolutionRecord[];
  analysis: Record<string, unknown> | null;
  isEvolving: boolean;

  triggerEvolution: (agentId: string, orgId: string) => Promise<void>;
  loadHistory: (agentId: string, orgId: string) => Promise<void>;
  loadPendingApprovals: (orgId: string) => Promise<void>;
  approveEvolution: (recordId: string, approved: boolean) => Promise<void>;
  runAnalysis: (agentId: string, orgId: string) => Promise<void>;
  runFeedbackLoop: (agentId: string, orgId: string) => Promise<void>;
}

export const useEvolverStore = create<EvolverState>((set) => ({
  history: [],
  pendingApprovals: [],
  analysis: null,
  isEvolving: false,

  triggerEvolution: async (agentId, orgId) => {
    set({ isEvolving: true });
    try {
      await apiRequest("/evolver/trigger", {
        method: "POST",
        body: { agent_id: agentId, org_id: orgId, async_exec: true },
      });
    } finally {
      set({ isEvolving: false });
    }
  },

  loadHistory: async (agentId, orgId) => {
    const result = await apiRequest<{ records: EvolutionRecord[] }>(
      `/evolver/history/${agentId}?org_id=${orgId}`
    );
    set({ history: result.records || [] });
  },

  loadPendingApprovals: async (orgId) => {
    const result = await apiRequest<{ records: EvolutionRecord[] }>(`/evolver/pending?org_id=${orgId}`);
    set({ pendingApprovals: result.records || [] });
  },

  approveEvolution: async (recordId, approved) => {
    await apiRequest("/evolver/approve", {
      method: "POST",
      body: { record_id: recordId, approved },
    });
  },

  runAnalysis: async (agentId, orgId) => {
    const result = await apiRequest<Record<string, unknown>>(`/evolver/analysis/${agentId}?org_id=${orgId}`);
    set({ analysis: result });
  },

  runFeedbackLoop: async (agentId, orgId) => {
    set({ isEvolving: true });
    try {
      await apiRequest(`/evolver/feedback-loop/${agentId}?org_id=${orgId}`);
    } finally {
      set({ isEvolving: false });
    }
  },
}));
