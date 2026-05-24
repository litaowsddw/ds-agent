"""Agent 与 Workspace MVP 存储。

该服务依赖 IdentityStore 做组织成员和 RBAC 校验。所有 Agent 操作都必须先确认
操作者属于目标组织，并拥有对应权限。
"""

from apps.api.app.domain.agent import Agent, AgentWorkspace, WorkspaceFileKind
from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission


DEFAULT_WORKSPACE_FILES: dict[WorkspaceFileKind, str] = {
    WorkspaceFileKind.AGENTS: "# AGENTS\n\n定义 Agent 的角色、目标和长期约束。\n",
    WorkspaceFileKind.SOUL: "# SOUL\n\n定义 Agent 的表达风格、偏好和协作方式。\n",
    WorkspaceFileKind.TOOLS: "# TOOLS\n\n记录 Agent 可用工具、MCP 服务和调用边界。\n",
    WorkspaceFileKind.MEMORY: "# MEMORY\n\n记录 Agent 的长期记忆摘要和人工确认事实。\n",
}


class AgentStore:
    """管理 Agent 和 Workspace。"""

    def __init__(self, identity: IdentityStore) -> None:
        # identity 是身份与权限服务，用于复用组织隔离和 RBAC。
        self.identity = identity

        # agents_by_id 保存 Agent 实体，key 是 agent_id。
        self.agents_by_id: dict[str, Agent] = {}

        # workspaces_by_agent_id 保存 Agent Workspace，key 是 agent_id。
        self.workspaces_by_agent_id: dict[str, AgentWorkspace] = {}

    def create_agent(
        self,
        actor_user_id: str,
        org_id: str,
        name: str,
        description: str,
        team_id: str | None = None,
    ) -> Agent:
        """创建 Agent 并初始化 Workspace。"""

        self.identity.assert_org_access(
            user_id=actor_user_id,
            org_id=org_id,
            permission=Permission.AGENT_CREATE,
        )

        if team_id is not None:
            self.identity._require_team_in_org(team_id=team_id, org_id=org_id)

        agent = Agent(
            agent_id=new_id("agt"),
            org_id=org_id,
            team_id=team_id,
            name=name.strip(),
            description=description.strip(),
            created_by=actor_user_id,
        )
        self.agents_by_id[agent.agent_id] = agent

        workspace = AgentWorkspace(
            workspace_id=new_id("wsp"),
            org_id=org_id,
            agent_id=agent.agent_id,
            files=dict(DEFAULT_WORKSPACE_FILES),
            updated_by=actor_user_id,
        )
        self.workspaces_by_agent_id[agent.agent_id] = workspace

        return agent

    def list_agents(self, actor_user_id: str, org_id: str) -> list[Agent]:
        """列出组织内 Agent。"""

        self.identity.assert_org_access(
            user_id=actor_user_id,
            org_id=org_id,
            permission=Permission.ORGANIZATION_READ,
        )

        return [agent for agent in self.agents_by_id.values() if agent.org_id == org_id]

    def get_agent(self, actor_user_id: str, agent_id: str) -> Agent:
        """读取单个 Agent。"""

        agent = self._require_agent(agent_id)
        self.identity.assert_org_access(
            user_id=actor_user_id,
            org_id=agent.org_id,
            permission=Permission.ORGANIZATION_READ,
        )
        return agent

    def get_workspace(self, actor_user_id: str, agent_id: str) -> AgentWorkspace:
        """读取 Agent Workspace。"""

        agent = self.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
        return self.workspaces_by_agent_id[agent.agent_id]

    def update_workspace_file(
        self,
        actor_user_id: str,
        agent_id: str,
        file_kind: WorkspaceFileKind,
        content: str,
    ) -> AgentWorkspace:
        """更新 Workspace 中的单个文件。"""

        agent = self._require_agent(agent_id)
        self.identity.assert_org_access(
            user_id=actor_user_id,
            org_id=agent.org_id,
            permission=Permission.AGENT_CREATE,
        )

        workspace = self.workspaces_by_agent_id[agent.agent_id]
        workspace.files[file_kind] = content
        workspace.updated_by = actor_user_id
        workspace.updated_at = utc_now()
        return workspace

    def _require_agent(self, agent_id: str) -> Agent:
        """要求 Agent 必须存在。"""

        agent = self.agents_by_id.get(agent_id)
        if agent is None:
            raise ValueError("Agent 不存在")
        return agent


# agent_store 是 MVP 阶段的进程内 Agent 存储。
agent_store = AgentStore(identity=identity_store)

