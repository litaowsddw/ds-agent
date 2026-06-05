/** Runtime 状态管理。
 *
 * 这个 store 只保存后端真实接口返回的数据。表单默认值保持为空，避免把示例供应商、
 * 示例工具或 mock 模型误展示成真实资源。
 */

import { create } from "zustand";
import type {
  BackgroundAgentItem,
  ContextBundle,
  LLMCallLog,
  MCPServer,
  MCPTool,
  MemoryItem,
  ModelProvider,
  SessionItem,
  Skill,
  SkillEvaluation,
} from "@/types/runtime";
import type { CacheStats } from "@/types/knowledge";
import { apiRequest } from "@/lib/api";

interface RuntimeStore {
  skills: Skill[];
  skillEvaluations: SkillEvaluation[];
  mcpServers: MCPServer[];
  mcpTools: MCPTool[];
  memories: MemoryItem[];
  sessions: SessionItem[];
  contextBundle: ContextBundle | null;
  modelProviders: ModelProvider[];
  gatewayLogs: LLMCallLog[];
  backgroundAgents: BackgroundAgentItem[];
  cacheStats: CacheStats | null;

  selectedProviderKey: string;
  selectedModel: string;

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

  setSkillForm: (form: { name: string; description: string }) => void;
  setMcpForm: (form: { serverName: string; url: string; toolName: string }) => void;
  setMemoryForm: (text: string) => void;
  setSessionInput: (text: string) => void;
  setProviderForm: (form: RuntimeStore["providerForm"]) => void;
  setSelectedProviderKey: (key: string) => void;
  setSelectedModel: (model: string) => void;

  createSkill: (actorUserId: string, orgId: string, agentId: string) => Promise<void>;
  suggestSkillEvaluationPatch: (actorUserId: string, evaluationId: string) => Promise<void>;
  createMcpTool: (actorUserId: string, orgId: string, agentId: string) => Promise<void>;
  createMemory: (actorUserId: string, agentId: string) => Promise<void>;
  saveModelProvider: (actorUserId: string, orgId: string) => Promise<void>;
  createSessionAndAssembleContext: (actorUserId: string, agentId: string) => Promise<void>;
  generateGatewayPreview: (actorUserId: string, orgId: string, prompt: string, temperature: number) => Promise<void>;
  refreshRuntimeData: (orgId: string, actorUserId: string, agentId?: string) => Promise<void>;
}

export const useRuntimeStore = create<RuntimeStore>((set, get) => ({
  skills: [],
  skillEvaluations: [],
  mcpServers: [],
  mcpTools: [],
  memories: [],
  sessions: [],
  contextBundle: null,
  modelProviders: [],
  gatewayLogs: [],
  backgroundAgents: [],
  cacheStats: null,

  selectedProviderKey: "",
  selectedModel: "",

  skillForm: { name: "", description: "" },
  mcpForm: { serverName: "", url: "", toolName: "" },
  memoryForm: "",
  sessionInput: "",
  providerForm: {
    providerKey: "",
    displayName: "",
    baseUrl: "",
    apiKey: "",
    models: "",
    defaultModel: "",
  },

  setSkillForm: (form) => set({ skillForm: form }),
  setMcpForm: (form) => set({ mcpForm: form }),
  setMemoryForm: (text) => set({ memoryForm: text }),
  setSessionInput: (text) => set({ sessionInput: text }),
  setProviderForm: (form) => set({ providerForm: form }),
  setSelectedProviderKey: (key) => {
    const provider = get().modelProviders.find((item) => item.provider_key === key);
    set({
      selectedProviderKey: key,
      selectedModel: provider?.default_model || provider?.models[0] || "",
    });
  },
  setSelectedModel: (model) => set({ selectedModel: model }),

  createSkill: async (actorUserId, orgId, agentId) => {
    const { skillForm } = get();
    if (!skillForm.name || !skillForm.description) {
      throw new Error("请填写 Skill 名称和说明");
    }
    const skill = await apiRequest<Skill>("/skills", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        org_id: orgId,
        scope: "organization",
        agent_id: agentId,
        content: `---\nname: ${skillForm.name}\ndescription: ${skillForm.description}\n---\n\n${skillForm.description}\n`,
      },
    });
    await apiRequest(`/skills/agents/${agentId}/policy`, {
      method: "PUT",
      body: { actor_user_id: actorUserId, skill_id: skill.skill_id, allowed: true },
    });
    set((state) => ({ skills: [skill, ...state.skills] }));
  },

  suggestSkillEvaluationPatch: async (actorUserId, evaluationId) => {
    const evaluation = await apiRequest<SkillEvaluation>(`/skill-evaluations/${evaluationId}/suggest`, {
      method: "POST",
      body: { actor_user_id: actorUserId },
    });
    set((state) => ({
      skillEvaluations: state.skillEvaluations.map((item) =>
        item.evaluation_id === evaluation.evaluation_id ? evaluation : item
      ),
    }));
  },

  createMcpTool: async (actorUserId, orgId, agentId) => {
    const { mcpForm } = get();
    if (!mcpForm.serverName || !mcpForm.url || !mcpForm.toolName) {
      throw new Error("请填写 MCP Server 名称、URL 和 Tool 名称");
    }
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
    const tool = await apiRequest<MCPTool>(`/mcp/servers/${server.server_id}/tools`, {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        name: mcpForm.toolName,
        description: "",
        input_schema: { type: "object", properties: { query: { type: "string" } } },
        risk_level: "low",
      },
    });
    await apiRequest(`/mcp/agents/${agentId}/policy`, {
      method: "PUT",
      body: { actor_user_id: actorUserId, server_id: server.server_id, allowed: true },
    });
    set((state) => ({
      mcpServers: [server, ...state.mcpServers],
      mcpTools: [tool, ...state.mcpTools],
    }));
  },

  createMemory: async (actorUserId, agentId) => {
    const { memoryForm } = get();
    if (!memoryForm.trim()) {
      throw new Error("请填写需要保存的记忆内容");
    }
    const memory = await apiRequest<MemoryItem>("/memory", {
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
    set((state) => ({ memories: [memory, ...state.memories] }));
  },

  saveModelProvider: async (actorUserId, orgId) => {
    const { providerForm } = get();
    const models = providerForm.models.split(",").map((model) => model.trim()).filter(Boolean);
    if (!providerForm.providerKey || !providerForm.displayName || !providerForm.baseUrl) {
      throw new Error("请填写模型供应商 Key、名称和 Base URL");
    }
    if (models.length === 0) {
      throw new Error("请至少填写一个真实模型名称");
    }
    const provider = await apiRequest<ModelProvider>("/model-providers", {
      method: "POST",
      body: {
        actor_user_id: actorUserId,
        org_id: orgId,
        provider_key: providerForm.providerKey,
        display_name: providerForm.displayName,
        base_url: providerForm.baseUrl,
        api_key: providerForm.apiKey,
        models,
        default_model: providerForm.defaultModel || models[0],
      },
    });
    set((state) => ({
      modelProviders: [
        provider,
        ...state.modelProviders.filter((item) => item.provider_key !== provider.provider_key),
      ],
      selectedProviderKey: provider.provider_key,
      selectedModel: provider.default_model || provider.models[0] || "",
    }));
  },

  createSessionAndAssembleContext: async (actorUserId, agentId) => {
    const { sessionInput } = get();
    if (!sessionInput.trim()) {
      throw new Error("请填写用户消息");
    }
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
    set((state) => ({
      contextBundle: context,
      sessions: [session, ...state.sessions],
    }));
  },

  generateGatewayPreview: async (actorUserId, orgId, prompt, temperature) => {
    const { selectedProviderKey, selectedModel } = get();
    if (!selectedProviderKey || !selectedModel) {
      throw new Error("请先选择真实模型供应商和模型");
    }
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
    const [skills, evaluations, servers, logs, providers, bgAgents, cacheStats] = await Promise.all([
      apiRequest<Skill[]>(`/skills?org_id=${orgId}&actor_user_id=${actorUserId}`),
      apiRequest<SkillEvaluation[]>(`/skill-evaluations?org_id=${orgId}&actor_user_id=${actorUserId}${agentId ? `&agent_id=${agentId}` : ""}`),
      apiRequest<MCPServer[]>(`/mcp/servers?org_id=${orgId}&actor_user_id=${actorUserId}`),
      apiRequest<LLMCallLog[]>("/gateway/llm/logs"),
      apiRequest<ModelProvider[]>(`/model-providers?org_id=${orgId}&actor_user_id=${actorUserId}`),
      apiRequest<BackgroundAgentItem[]>(`/background-agents?org_id=${orgId}&actor_user_id=${actorUserId}`),
      apiRequest<CacheStats>("/cache/stats"),
    ]);

    set((state) => {
      const selectedStillExists = providers.some(
        (provider) => provider.provider_key === state.selectedProviderKey
      );
      const selectedProviderKey = selectedStillExists
        ? state.selectedProviderKey
        : providers[0]?.provider_key ?? "";
      const selectedProvider = providers.find(
        (provider) => provider.provider_key === selectedProviderKey
      );
      return {
        skills,
        skillEvaluations: evaluations,
        mcpServers: servers,
        gatewayLogs: logs,
        modelProviders: providers,
        backgroundAgents: bgAgents,
        cacheStats,
        selectedProviderKey,
        selectedModel: selectedProvider?.default_model || selectedProvider?.models[0] || "",
      };
    });

    if (agentId) {
      const [sessions, memories, tools] = await Promise.all([
        apiRequest<SessionItem[]>(`/sessions?agent_id=${agentId}&actor_user_id=${actorUserId}`),
        apiRequest<MemoryItem[]>(`/memory?agent_id=${agentId}&actor_user_id=${actorUserId}`),
        apiRequest<MCPTool[]>(`/mcp/agents/${agentId}/tools?actor_user_id=${actorUserId}`),
      ]);
      set({ sessions, memories, mcpTools: tools });
    } else {
      set({ sessions: [], memories: [], mcpTools: [] });
    }
  },
}));
