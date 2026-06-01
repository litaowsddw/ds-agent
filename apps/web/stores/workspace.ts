/** Workspace 状态管理。

管理当前工作空间、用户信息、Agent 列表等核心状态。
 */

import { create } from "zustand";
import type { Agent, WorkspaceState, CreateAgentRequest } from "@/types/agent";
import { apiRequest } from "@/lib/api";

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
  createAgent: (form: { name: string; description: string }) => Promise<void>;

  /** 刷新 Agent 列表 */
  refreshAgents: () => Promise<void>;

  /** 获取当前选中的 Agent */
  getSelectedAgent: () => Agent | null;
}

export const useWorkspaceStore = create<WorkspaceStore>((set, get) => ({
  workspace: null,
  agents: [],
  selectedAgentId: "",
  busy: false,
  apiStatus: "checking",

  setWorkspace: (ws) => set({ workspace: ws }),
  setAgents: (agents) => set({ agents }),
  setSelectedAgentId: (id) => set({ selectedAgentId: id }),
  setBusy: (busy) => set({ busy }),
  setApiStatus: (status) => set({ apiStatus: status }),

  createWorkspace: async (form) => {
    set({ busy: true });
    try {
      const timestamp = Date.now();
      const email = form.email.includes("@")
        ? form.email
        : `owner-${timestamp}@example.com`;

      const user = await apiRequest<{ user_id: string }>("/identity/users/register", {
        method: "POST",
        body: {
          email: email.replace("@example.com", `-${timestamp}@example.com`),
          display_name: form.displayName,
          password: "password123",
        },
      });

      const organization = await apiRequest<{ org_id: string }>("/identity/organizations", {
        method: "POST",
        body: { creator_user_id: user.user_id, name: form.orgName },
      });

      const team = await apiRequest<{ team_id: string }>(
        `/identity/organizations/${organization.org_id}/teams`,
        {
          method: "POST",
          body: { actor_user_id: user.user_id, name: form.teamName },
        }
      );

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

  refreshAgents: async () => {
    const { workspace } = get();
    if (!workspace) return;

    const agents = await apiRequest<Agent[]>(
      `/agents?org_id=${workspace.orgId}&actor_user_id=${workspace.userId}`
    );
    set({ agents });
  },

  getSelectedAgent: () => {
    const { agents, selectedAgentId } = get();
    return agents.find((a) => a.agent_id === selectedAgentId) ?? null;
  },
}));
