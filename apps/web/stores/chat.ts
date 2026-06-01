import { create } from "zustand";
import { apiRequest } from "@/lib/api";
import { wsManager } from "@/lib/websocket";

/** 消息 */
export interface Message {
  message_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sequence: number;
  meta_info?: Record<string, unknown>;
  created_at: string;
}

/** Chat 状态 */
interface ChatState {
  /** 当前会话 ID */
  sessionId: string | null;
  /** 消息列表 */
  messages: Message[];
  /** 是否正在生成 */
  isGenerating: boolean;
  /** 当前 Agent */
  agentId: string | null;
  /** 意图识别结果 */
  intent: string;
  /** 子任务数 */
  subtaskCount: number;

  // Actions
  /** 发送消息 */
  sendMessage: (agentId: string, orgId: string, message: string) => Promise<void>;
  /** 加载会话消息 */
  loadMessages: (sessionId: string) => Promise<void>;
  /** 清空会话 */
  clearSession: () => void;
  /** 订阅实时消息 */
  subscribeMessages: () => () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: null,
  messages: [],
  isGenerating: false,
  agentId: null,
  intent: "",
  subtaskCount: 0,

  sendMessage: async (agentId, orgId, message) => {
    set({ isGenerating: true, agentId });

    // 添加用户消息到列表
    const userMsg: Message = {
      message_id: `temp_${Date.now()}`,
      role: "user",
      content: message,
      sequence: get().messages.length,
      created_at: new Date().toISOString(),
    };
    set((state) => ({ messages: [...state.messages, userMsg] }));

    try {
      const result = await apiRequest<{
        response: string;
        session_id: string;
        mode: string;
        intent: string;
        subtask_count: number;
        plan_id: string;
      }>("/chat/", {
        method: "POST",
        body: {
          agent_id: agentId,
          org_id: orgId,
          message,
          session_id: get().sessionId,
        },
      });

      // 添加助手消息
      const assistantMsg: Message = {
        message_id: `resp_${Date.now()}`,
        role: "assistant",
        content: result.response,
        sequence: get().messages.length,
        meta_info: { intent: result.intent, plan_id: result.plan_id },
        created_at: new Date().toISOString(),
      };

      set((state) => ({
        messages: [...state.messages, assistantMsg],
        sessionId: result.session_id,
        intent: result.intent,
        subtaskCount: result.subtask_count,
        isGenerating: false,
      }));
    } catch {
      const errorMsg: Message = {
        message_id: `err_${Date.now()}`,
        role: "system",
        content: "消息发送失败，请重试。",
        sequence: get().messages.length,
        created_at: new Date().toISOString(),
      };
      set((state) => ({
        messages: [...state.messages, errorMsg],
        isGenerating: false,
      }));
    }
  },

  loadMessages: async (sessionId) => {
    try {
      const result = await apiRequest<{
        messages: Message[];
      }>(`/chat/sessions/${sessionId}/messages`);
      set({ sessionId, messages: result.messages || [] });
    } catch {
      // 加载失败，保持空列表
    }
  },

  clearSession: () => {
    set({ sessionId: null, messages: [], intent: "", subtaskCount: 0 });
  },

  subscribeMessages: () => {
    return wsManager.on("chat_message", (_event, data) => {
      const msg = data as Message;
      set((state) => ({ messages: [...state.messages, msg] }));
    });
  },
}));

/** Evolver 进化记录 */
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

/** Evolver 状态 */
interface EvolverState {
  /** 进化历史 */
  history: EvolutionRecord[];
  /** 待审批列表 */
  pendingApprovals: EvolutionRecord[];
  /** 分析结果 */
  analysis: Record<string, unknown> | null;
  /** 是否正在进化 */
  isEvolving: boolean;

  // Actions
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
    const result = await apiRequest<{ records: EvolutionRecord[] }>(
      `/evolver/pending?org_id=${orgId}`
    );
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
