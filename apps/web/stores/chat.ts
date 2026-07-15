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
  messages: Message[];
  traceEvents: ChatTraceEvent[];
  isGenerating: boolean;
  agentId: string | null;
  intent: string;
  subtaskCount: number;
  failedSendSnapshot: FailedSendSnapshot | null;

  sendMessage: (
    agentId: string,
    orgId: string,
    message: string,
    actorUserId?: string,
    options?: SendMessageOptions
  ) => Promise<void>;
  retryLastMessage: () => Promise<void>;
  loadLatestSession: (agentId: string, actorUserId: string) => Promise<void>;
  loadMessages: (sessionId: string) => Promise<void>;
  clearSession: () => void;
  subscribeMessages: () => () => void;
}

let activeChatGeneration = 0;

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: null,
  messages: [],
  traceEvents: [],
  isGenerating: false,
  agentId: null,
  intent: "",
  subtaskCount: 0,
  failedSendSnapshot: null,

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
    set({ isGenerating: true, agentId, traceEvents: [], failedSendSnapshot: null });

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
            set({
              sessionId: String(data.session_id ?? get().sessionId ?? ""),
              isGenerating: false,
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
      messages: [],
      traceEvents: [],
      failedSendSnapshot: null,
      isGenerating: false,
      intent: "",
      subtaskCount: 0,
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

  loadMessages: async (sessionId) => {
    try {
      const result = await apiRequest<{ messages: Message[] }>(`/chat/sessions/${sessionId}/messages`);
      set({ sessionId, messages: result.messages || [] });
    } catch {
      // Keep the current local messages when history loading fails.
    }
  },

  clearSession: () => {
    activeChatGeneration += 1;
    set({
      sessionId: null,
      messages: [],
      traceEvents: [],
      intent: "",
      subtaskCount: 0,
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
