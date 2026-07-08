"""Agent 与 Workspace 数据库服务。

替换 agent_store.py 的内存实现，使用 SQLAlchemy 异步操作 MySQL。
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentModel, AgentWorkspaceModel
from app.services.db.base import BaseDBService


# 默认 Workspace 文件内容
DEFAULT_WORKSPACE_FILES: dict[str, str] = {
    "agents_md": "# AGENTS\n\n定义 Agent 的角色、目标和长期约束。\n",
    "soul_md": "# SOUL\n\n定义 Agent 的表达风格、偏好和协作方式。\n",
    "tools_md": "# TOOLS\n\n记录 Agent 可用工具、MCP 服务和调用边界。\n",
    "memory_md": "# MEMORY\n\n记录 Agent 的长期记忆摘要和人工确认事实。\n",
}


class AgentDBService(BaseDBService[AgentModel]):
    """Agent 数据库服务。"""

    def __init__(self) -> None:
        super().__init__(AgentModel)

    async def create_agent(
        self,
        session: AsyncSession,
        agent_id: str,
        org_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
        team_id: str | None = None,
        kind: str = "USER_SUB",
        workspace_id: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = 0.0,
        max_tokens: int | None = None,
        default_workflow_id: str | None = None,
    ) -> AgentModel:
        """创建 Agent。"""
        agent = AgentModel(
            agent_id=agent_id,
            org_id=org_id,
            team_id=team_id,
            name=name.strip(),
            description=description.strip(),
            kind=kind,
            workspace_id=workspace_id,
            model_provider=model_provider,
            model_name=model_name,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            default_workflow_id=default_workflow_id,
            created_by=created_by,
        )
        session.add(agent)
        await session.flush()
        return agent

    async def list_org_agents(
        self,
        session: AsyncSession,
        org_id: str,
        kind: str | None = None,
    ) -> list[AgentModel]:
        """列出组织内 Agent。"""
        stmt = select(AgentModel).where(AgentModel.org_id == org_id)
        if kind is not None:
            stmt = stmt.where(AgentModel.kind == kind)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_agent_required(self, session: AsyncSession, agent_id: str) -> AgentModel:
        """获取 Agent，不存在则抛出 ValueError。"""
        return await self.get_by_id_required(session, agent_id, "agent_id")

    async def update_agent(
        self, session: AsyncSession, agent_id: str, **data
    ) -> AgentModel:
        """更新 Agent。"""
        agent = await self.get_agent_required(session, agent_id)
        for key, value in data.items():
            if hasattr(agent, key) and (value is not None or key == "default_workflow_id"):
                setattr(agent, key, value)
        await session.flush()
        return agent

    async def delete_agent(self, session: AsyncSession, agent_id: str) -> bool:
        """删除 Agent。"""
        return await self.delete_by_id(session, agent_id)


class AgentWorkspaceDBService(BaseDBService[AgentWorkspaceModel]):
    """Agent Workspace 数据库服务。"""

    def __init__(self) -> None:
        super().__init__(AgentWorkspaceModel)

    async def create_workspace(
        self,
        session: AsyncSession,
        workspace_id: str,
        org_id: str,
        agent_id: str,
        updated_by: str,
    ) -> AgentWorkspaceModel:
        """为 Agent 创建 Workspace。"""
        workspace = AgentWorkspaceModel(
            workspace_id=workspace_id,
            org_id=org_id,
            agent_id=agent_id,
            agents_md=DEFAULT_WORKSPACE_FILES["agents_md"],
            soul_md=DEFAULT_WORKSPACE_FILES["soul_md"],
            tools_md=DEFAULT_WORKSPACE_FILES["tools_md"],
            memory_md=DEFAULT_WORKSPACE_FILES["memory_md"],
            updated_by=updated_by,
        )
        session.add(workspace)
        await session.flush()
        return workspace

    async def get_by_agent_id(
        self, session: AsyncSession, agent_id: str
    ) -> AgentWorkspaceModel | None:
        """根据 agent_id 获取 Workspace。"""
        stmt = select(AgentWorkspaceModel).where(
            AgentWorkspaceModel.agent_id == agent_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_agent_id_required(
        self, session: AsyncSession, agent_id: str
    ) -> AgentWorkspaceModel:
        """根据 agent_id 获取 Workspace，不存在则抛出异常。"""
        workspace = await self.get_by_agent_id(session, agent_id)
        if workspace is None:
            raise ValueError("Workspace 不存在")
        return workspace

    async def update_workspace_file(
        self,
        session: AsyncSession,
        agent_id: str,
        file_field: str,
        content: str,
        updated_by: str,
    ) -> AgentWorkspaceModel:
        """更新 Workspace 中的单个文件。

        file_field 可以是 agents_md, soul_md, tools_md, memory_md。
        """
        workspace = await self.get_by_agent_id_required(session, agent_id)
        if not hasattr(workspace, file_field):
            raise ValueError(f"Workspace 文件字段不存在：{file_field}")
        setattr(workspace, file_field, content)
        workspace.updated_by = updated_by
        await session.flush()
        return workspace

    async def get_workspace_files(
        self, session: AsyncSession, agent_id: str
    ) -> dict[str, str]:
        """获取 Workspace 所有文件内容。"""
        workspace = await self.get_by_agent_id_required(session, agent_id)
        return {
            "agents_md": workspace.agents_md,
            "soul_md": workspace.soul_md,
            "tools_md": workspace.tools_md,
            "memory_md": workspace.memory_md,
        }


# 全局数据库服务实例
agent_db = AgentDBService()
workspace_db = AgentWorkspaceDBService()
