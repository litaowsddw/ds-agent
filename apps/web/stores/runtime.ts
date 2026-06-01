/** Runtime 状态管理。

管理 Skill、MCP、Memory、Session、Model Provider、Gateway 等运行时状态。
 */

import { create } from "zustand";
import type {
  Skill,
  MCPServer,
  MCPTool,
  MemoryItem,
  SessionItem,
  ContextBundle,
  ModelProvider,
  LLMCallLog,
  BackgroundAgentItem,
} from "@/types/runtime";
import type { CacheStats } from "@/types/knowledge";
import { apiRequest } from "@/lib/api";

interface RuntimeStore {
  // 资源列表
  skills: Skill[];
  mcpServers: MCPServer[];
  mcpTools: MCPTool[];
  memories: MemoryItem[];
  sessions: SessionItem[];
  contextBundle: ContextBundle | null;
  modelProviders: ModelProvider[];
  gatewayLogs: LLMCallLog[];
  backgroundAgents: BackgroundAgentItem[];
  cacheStats: CacheStats | null;

  // 模型选择
  selectedProviderKey: string;
  selectedModel: string;

  // 表单状态
  skillForm: { name: string; description: string };
  mcpForm: { serverName: string; url: string; toolName: string };
  memoryForm: string;
  sessionInput: string;
  providerForm: {
    providerKey: string;
    displayName: string;
    baseUrl: string;
    apiKey: string;
    models: string;
    defaultModel: string;
  };

  // Actions - Setters
  setSkillForm: (form: { name: string; description: string }) => void;
  setMcpForm: (form: { serverName: string; url: string; toolName: string }) => void;
  setMemoryForm: (text: string) => void;
  setSessionInput: (text: string) => void;
  setProviderForm: (form: {
    providerKey: string;
    displayName: string;
    baseUrl: string;
    apiKey: string;
    models: string;
    defaultModel: string;
  }) => void;
  setSelectedProviderKey: (key: string) => void;
  setSelectedModel: (model: string) => void;

  // Actions - API
  createSkill: (actorUserId: string, orgId: string, agentId: string) => Promise<void>;
  createMcpTool: (actorUserId: string, orgId: string, agentId: string) => Promise<void>;
  createMemory: (actorUserId: string, agentId: string) => Promise<void>;
  saveModelProvider: (actorUserId: string, orgId: string) => Promise<void>;
  createSessionAndAssembleContext: (actorUserId: string, agentId: string) => Promise<void>;
  generateGatewayPreview: (actorUserId: string, orgId: string, prompt: string, temperature: number) => Promise<void>;
  refreshRuntimeData: (orgId: string, actorUserId: string, agentId?: string) => Promise<void>;
}

export const useRuntimeStore = create<RuntimeStore>((set, get) => ({
  skills: [],
  mcpServers: [],
  mcpTools: [],
  memories: [],
  sessions: [],
  contextBundle: null,
  modelProviders: [],
  gatewayLogs: [],
  backgroundAgents: [],
  cacheStats: null,

  selectedProviderKey: "mock",
  selectedModel: "mock-model",

  skillForm: { name: "workflow-reviewer", description: "检查工作流结构并给出改进建议" },
  mcpForm: { serverName: "知识库 MCP", url: "http://localhost:18080/mcp", toolName: "search_docs" },
  memoryForm: "用户偏好中文、先给结论、再给验证证据。",
  sessionInput: "请结合工作区、Skill、MCP 和 Memory 输出一次响应。",
  providerForm: {
    providerKey: "deepseek",
    displayName: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    apiKey: "",
    models: "deepseek-chat, deepseek-reasoner",
    defaultModel: "deepseek-chat",
  },

  setSkillForm: (form) => set({ skillForm: form }),
  setMcpForm: (form) => set({ mcpForm: form }),
  setMemoryForm: (text) => set({ memoryForm: text }),
  setSessionInput: (text) => set({ sessionInput: text }),
  setProviderForm: (form) => set({ providerForm: form }),
  setSelectedProviderKey: (key) => {
    const { modelProviders } = get();
    const provider = modelProviders.find((p) => p.provider_key === key);
    set({
      selectedProviderKey: key,
      selectedModel: provider?.default_model || provider?.models[0] || "mock-model",
    });
  },
  setSelectedModel: (model) => set({ selectedModel: model }),

  createSkill: async (actorUserId, orgId, agentId) => {
    const { skillForm } = get();
    const skill = await apiRequest<Skill>("/skills", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        org_id: orgId,
        scope: "organization",
        agent_id: agentId,
        content: `---\nname: ${skillForm.name}\ndescription: ${skillForm.description}\n---\n\n优先检查输入、输出、错误处理和运行证据。\n`,
      },
    });
    await apiRequest(`/skills/agents/${agentId}/policy`, {
      method: "PUT",
      body: { actor_user_id: actorUserId, skill_id: skill.skill_id, allowed: true },
    });
    set((state) => ({ skills: [...state.skills, skill] }));
  },

  createMcpTool: async (actorUserId, orgId, agentId) => {
    const { mcpForm } = get();
    const server = await apiRequest<MCPServer>("/mcp/servers", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        org_id: orgId,
        name: mcpForm.serverName,
        transport: "http",
        url: mcpForm.url,
      },
    });
    await apiRequest<MCPTool>(`/mcp/servers/${server.server_id}/tools`, {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        name: mcpForm.toolName,
        description: "检索内部知识库文档。",
        input_schema: { type: "object", properties: { query: { type: "string" } } },
        risk_level: "low",
      },
    });
    await apiRequest(`/mcp/agents/${agentId}/policy`, {
      method: "PUT",
      body: { actor_user_id: actorUserId, server_id: server.server_id, allowed: true },
    });
    set((state) => ({ mcpServers: [...state.mcpServers, server] }));
  },

  createMemory: async (actorUserId, agentId) => {
    const { memoryForm } = get();
    await apiRequest<MemoryItem>("/memory", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        agent_id: agentId,
        memory_type: "preference",
        content: memoryForm,
        summary: memoryForm,
        confidence: 0.95,
        source: "studio",
      },
    });
  },

  saveModelProvider: async (actorUserId, orgId) => {
    const { providerForm } = get();
    const provider = await apiRequest<ModelProvider>("/model-providers", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        org_id: orgId,
        provider_key: providerForm.providerKey,
        display_name: providerForm.displayName,
        base_url: providerForm.baseUrl,
        api_key: providerForm.apiKey,
        models: providerForm.models.split(",").map((m) => m.trim()).filter(Boolean),
        default_model: providerForm.defaultModel,
      },
    });
    set((state) => ({ modelProviders: [...state.modelProviders, provider] }));
  },

  createSessionAndAssembleContext: async (actorUserId, agentId) => {
    const { sessionInput } = get();
    const session = await apiRequest<SessionItem>("/sessions", {
      method: "POST",
      body: { actor_user_id: actorUserId, agent_id: agentId, queue_mode: "queue" },
    });
    await apiRequest(`/sessions/${session.session_id}/messages`, {
      method: "POST",
      body: { actor_user_id: actorUserId, role: "user", content: sessionInput },
    });
    const context = await apiRequest<ContextBundle>(
      `/context/sessions/${session.session_id}/assemble?actor_user_id=${actorUserId}&current_input=${encodeURIComponent(sessionInput)}&token_budget=4096`
    );
    set({ contextBundle: context });
    set((state) => ({ sessions: [...state.sessions, session] }));
  },

  generateGatewayPreview: async (actorUserId, orgId, prompt, temperature) => {
    const { selectedProviderKey, selectedModel } = get();
    await apiRequest("/gateway/llm/generate", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        org_id: orgId,
        provider: selectedProviderKey,
        model: selectedModel,
        prompt,
        parameters: { temperature },
      },
    });
    const logs = await apiRequest<LLMCallLog[]>("/gateway/llm/logs");
    set({ gatewayLogs: logs });
  },

  refreshRuntimeData: async (orgId, actorUserId, agentId) => {
    const [skills, servers, logs, providers, bgAgents, cacheStats] = await Promise.all([
      apiRequest<Skill[]>(`/skills?org_id=${orgId}&actor_user_id=${actorUserId}`),
      apiRequest<MCPServer[]>(`/mcp/servers?org_id=${orgId}&actor_user_id=${actorUserId}`),
      apiRequest<LLMCallLog[]>("/gateway/llm/logs"),
      apiRequest<ModelProvider[]>(`/model-providers?org_id=${orgId}&actor_user_id=${actorUserId}`),
      apiRequest<BackgroundAgentItem[]>(`/background-agents?org_id=${orgId}&actor_user_id=${actorUserId}`),
      apiRequest<CacheStats>("/cache/stats"),
    ]);

    set({ skills, mcpServers: servers, gatewayLogs: logs, modelProviders: providers, backgroundAgents: bgAgents, cacheStats });

    if (agentId) {
      const [sessions, memories, tools] = await Promise.all([
        apiRequest<SessionItem[]>(`/sessions?agent_id=${agentId}&actor_user_id=${actorUserId}`),
        apiRequest<MemoryItem[]>(`/memory?agent_id=${agentId}&actor_user_id=${actorUserId}`),
        apiRequest<MCPTool[]>(`/mcp/agents/${agentId}/tools?actor_user_id=${actorUserId}`),
      ]);
      set({ sessions, memories, mcpTools: tools });
    }
  },
}));
