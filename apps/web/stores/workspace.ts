/** Workspace 状态管理。

管理当前工作空间、用户信息、Agent 列表等核心状态。
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Agent, WorkspaceState } from "@/types/agent";
import { apiRequest, clearCurrentOrgId, login, setCurrentOrgId } from "@/lib/api";
import { useWorkflowStore } from "@/stores/workflow";

interface WorkspaceStore {
  /** 当前工作空间 */
  workspace: WorkspaceState | null;
  /** Agent 列表 */
  agents: Agent[];
  /** 当前选中的 Agent ID */
  selectedAgentId: string;
  /** 全局加载状态 */
  busy: boolean;
  /** API 连接状态 */
  apiStatus: "checking" | "online" | "offline";

  // Actions
  setWorkspace: (ws: WorkspaceState | null) => void;
  setAgents: (agents: Agent[]) => void;
  setSelectedAgentId: (id: string) => void;
  setBusy: (busy: boolean) => void;
  setApiStatus: (status: "checking" | "online" | "offline") => void;

  /** 创建工作空间（注册用户 + 创建组织 + 创建团队） */
  createWorkspace: (form: {
    email: string;
    displayName: string;
    orgName: string;
    teamName: string;
  }) => Promise<void>;

  /** 创建 Agent */
  createAgent: (form: {
    name: string;
    description: string;
    modelProvider?: string;
    modelName?: string;
    systemPrompt?: string;
    temperature?: number | null;
    maxTokens?: number | null;
    defaultWorkflowId?: string | null;
  }) => Promise<void>;

  /** 更新 Agent 参数 */
  updateAgent: (agentId: string, form: {
    name: string;
    description: string;
    modelProvider?: string;
    modelName?: string;
    systemPrompt?: string;
    temperature?: number | null;
    maxTokens?: number | null;
    defaultWorkflowId?: string | null;
  }) => Promise<void>;

  /** 刷新 Agent 列表 */
  refreshAgents: () => Promise<void>;

  /** 获取当前选中的 Agent */
  getSelectedAgent: () => Agent | null;
}

export const useWorkspaceStore = create<WorkspaceStore>()(
persist((set, get) => ({
  workspace: null,
  agents: [],
  selectedAgentId: "",
  busy: false,
  apiStatus: "checking",

  setWorkspace: (ws) => {
    if (ws) {
      setCurrentOrgId(ws.orgId);
      set({ workspace: ws });
      return;
    }
    clearCurrentOrgId();
    useWorkflowStore.getState().resetWorkspaceData();
    set({ workspace: null, agents: [], selectedAgentId: "" });
  },
  setAgents: (agents) => set((state) => ({
    agents,
    selectedAgentId: agents.some((a) => a.agent_id === state.selectedAgentId)
      ? state.selectedAgentId : agents.length === 1 ? agents[0].agent_id : "",
  })),
  setSelectedAgentId: (id) => {
    if (get().selectedAgentId !== id) {
      useWorkflowStore.getState().clearRunSelection();
    }
    set({ selectedAgentId: id });
  },
  setBusy: (busy) => set({ busy }),
  setApiStatus: (status) => set({ apiStatus: status }),

  createWorkspace: async (form) => {
    set({ busy: true });
    try {
      const email = form.email.trim();
      if (!email || !form.displayName.trim()) {
        throw new Error("请填写邮箱和显示名称");
      }

      const user = await ensureLocalUser(email, form.displayName);
      const organization = await ensureOrganization(user.user_id, form.orgName.trim() || "AgentFlow 工作空间");
      setCurrentOrgId(organization.org_id);
      const team = await ensureTeam(user.user_id, organization.org_id, form.teamName.trim() || "默认团队");

      set({
        workspace: {
          userId: user.user_id,
          orgId: organization.org_id,
          teamId: team.team_id,
          email,
        },
      });
    } finally {
      set({ busy: false });
    }
  },

  createAgent: async (form) => {
    const { workspace } = get();
    if (!workspace) throw new Error("请先创建工作空间。");
    if (!form.name.trim()) throw new Error("请填写 Agent 名称");

    set({ busy: true });
    try {
      const agent = await apiRequest<Agent>("/agents", {
        method: "POST",
        body: {
          actor_user_id: workspace.userId,
          org_id: workspace.orgId,
          team_id: workspace.teamId,
          name: form.name,
          description: form.description,
          model_provider: form.modelProvider || null,
          model_name: form.modelName || null,
          system_prompt: form.systemPrompt || null,
          temperature: form.temperature ?? 0,
          max_tokens: form.maxTokens ?? null,
          default_workflow_id: form.defaultWorkflowId ?? null,
        },
      });
      set((state) => ({
        agents: [...state.agents, agent],
        selectedAgentId: agent.agent_id,
      }));
    } finally {
      set({ busy: false });
    }
  },

  updateAgent: async (agentId, form) => {
    const { workspace } = get();
    if (!workspace) throw new Error("请先创建工作空间。");
    if (!agentId) throw new Error("请先选择 Agent");
    if (!form.name.trim()) throw new Error("请填写 Agent 名称");

    set({ busy: true });
    try {
      const agent = await apiRequest<Agent>(`/agents/${agentId}`, {
        method: "PUT",
        body: {
          actor_user_id: workspace.userId,
          name: form.name,
          description: form.description,
          model_provider: form.modelProvider || null,
          model_name: form.modelName || null,
          system_prompt: form.systemPrompt || null,
          temperature: form.temperature ?? 0,
          max_tokens: form.maxTokens ?? null,
          default_workflow_id: form.defaultWorkflowId ?? null,
        },
      });
      set((state) => ({
        agents: state.agents.map((item) => (item.agent_id === agent.agent_id ? agent : item)),
        selectedAgentId: agent.agent_id,
      }));
    } finally {
      set({ busy: false });
    }
  },

  refreshAgents: async () => {
    const { workspace } = get();
    if (!workspace) return;

    const agents = await apiRequest<Agent[]>(
      `/agents?org_id=${workspace.orgId}&actor_user_id=${workspace.userId}`
    );
    get().setAgents(agents);
  },

  getSelectedAgent: () => {
    const { agents, selectedAgentId } = get();
    return agents.find((a) => a.agent_id === selectedAgentId) ?? null;
  },
}), {
  name: "agentflow-workspace",
  storage: createJSONStorage(() => localStorage),
  partialize: (state) => ({
    workspace: state.workspace,
    agents: state.agents,
    selectedAgentId: state.selectedAgentId,
  }),
}));

const LOCAL_DEFAULT_PASSWORD = "password123";

interface LocalUser {
  user_id: string;
  email: string;
  display_name?: string;
}

interface LocalOrganization {
  org_id: string;
  name?: string;
  created_by?: string;
}

interface LocalTeam {
  team_id: string;
  org_id: string;
  name?: string;
}

async function ensureLocalUser(email: string, displayName: string): Promise<LocalUser> {
  try {
    await apiRequest<LocalUser>("/identity/users/register", {
      method: "POST",
      body: {
        email,
        display_name: displayName,
        password: LOCAL_DEFAULT_PASSWORD,
      },
    });
  } catch (error) {
    if (!isDuplicateEmailError(error)) {
      throw error;
    }
  }

  try {
    const session = await login({ email, password: LOCAL_DEFAULT_PASSWORD });
    return {
      user_id: session.user.user_id,
      email: session.user.email,
      display_name: session.user.display_name,
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`该邮箱已存在，但无法用本地默认密码恢复登录：${detail}`);
  }
}

async function ensureOrganization(userId: string, orgName: string): Promise<LocalOrganization> {
  const organizations = await apiRequest<LocalOrganization[]>(`/identity/users/${userId}/organizations`);
  if (organizations.length > 0) {
    return organizations[0];
  }
  return apiRequest<LocalOrganization>("/identity/organizations", {
    method: "POST",
    body: { creator_user_id: userId, name: orgName },
  });
}

async function ensureTeam(userId: string, orgId: string, teamName: string): Promise<LocalTeam> {
  const teams = await apiRequest<LocalTeam[]>(`/identity/organizations/${orgId}/teams?actor_user_id=${userId}`);
  if (teams.length > 0) {
    return teams[0];
  }
  return apiRequest<LocalTeam>(`/identity/organizations/${orgId}/teams`, {
    method: "POST",
    body: { actor_user_id: userId, name: teamName },
  });
}

function isDuplicateEmailError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.includes("邮箱已注册") || message.includes("already") || message.includes("宸叉敞鍐");
}
