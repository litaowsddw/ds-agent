"""运行时资源数据库服务（Skill、MCP、Memory、ModelProvider、BackgroundAgent）。

替换内存 store，使用 SQLAlchemy 异步操作 MySQL。
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runtime import (
    SkillModel,
    AgentSkillPolicyModel,
    MCPServerModel,
    MCPToolModel,
    AgentMCPPolicyModel,
    MemoryModel,
    ModelProviderModel,
    BackgroundAgentModel,
)
from app.services.db.base import BaseDBService


class SkillDBService(BaseDBService[SkillModel]):
    """Skill 数据库服务。"""

    def __init__(self) -> None:
        super().__init__(SkillModel)

    async def create_skill(
        self,
        session: AsyncSession,
        skill_id: str,
        org_id: str,
        name: str,
        scope: str = "organization",
        description: str = "",
        content: str = "",
        team_id: str | None = None,
        agent_id: str | None = None,
        file_path: str | None = None,
        created_by: str = "",
    ) -> SkillModel:
        """创建 Skill。"""
        skill = SkillModel(
            skill_id=skill_id,
            org_id=org_id,
            team_id=team_id,
            agent_id=agent_id,
            scope=scope,
            name=name,
            description=description,
            content=content,
            file_path=file_path,
            created_by=created_by,
        )
        session.add(skill)
        await session.flush()
        return skill

    async def list_org_skills(
        self,
        session: AsyncSession,
        org_id: str,
        scope: str | None = None,
    ) -> list[SkillModel]:
        """列出组织 Skill。"""
        stmt = select(SkillModel).where(SkillModel.org_id == org_id)
        if scope is not None:
            stmt = stmt.where(SkillModel.scope == scope)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_agent_allowed_skills(
        self,
        session: AsyncSession,
        agent_id: str,
        org_id: str,
    ) -> list[SkillModel]:
        """列出 Agent 授权可用的 Skill。"""
        # 查找 Agent 的授权策略
        policy_stmt = select(AgentSkillPolicyModel.skill_id).where(
            AgentSkillPolicyModel.agent_id == agent_id,
            AgentSkillPolicyModel.allowed == True,
        )
        policy_result = await session.execute(policy_stmt)
        allowed_skill_ids = [row[0] for row in policy_result.all()]

        if not allowed_skill_ids:
            return []

        stmt = select(SkillModel).where(
            SkillModel.org_id == org_id,
            SkillModel.skill_id.in_(allowed_skill_ids),
            SkillModel.enabled == True,
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class AgentSkillPolicyDBService(BaseDBService[AgentSkillPolicyModel]):
    """Agent Skill 授权策略数据库服务。"""

    def __init__(self) -> None:
        super().__init__(AgentSkillPolicyModel)

    async def set_policy(
        self,
        session: AsyncSession,
        agent_id: str,
        skill_id: str,
        allowed: bool = True,
    ) -> AgentSkillPolicyModel:
        """设置授权策略。"""
        # 查找已有策略
        stmt = select(AgentSkillPolicyModel).where(
            AgentSkillPolicyModel.agent_id == agent_id,
            AgentSkillPolicyModel.skill_id == skill_id,
        )
        result = await session.execute(stmt)
        policy = result.scalar_one_or_none()

        if policy is not None:
            policy.allowed = allowed
        else:
            policy = AgentSkillPolicyModel(
                agent_id=agent_id,
                skill_id=skill_id,
                allowed=allowed,
            )
            session.add(policy)
        await session.flush()
        return policy


class MCPServerDBService(BaseDBService[MCPServerModel]):
    """MCP Server 数据库服务。"""

    def __init__(self) -> None:
        super().__init__(MCPServerModel)

    async def create_server(
        self,
        session: AsyncSession,
        server_id: str,
        org_id: str,
        name: str,
        url: str,
        transport: str = "http",
        created_by: str = "",
    ) -> MCPServerModel:
        """注册 MCP Server。"""
        server = MCPServerModel(
            server_id=server_id,
            org_id=org_id,
            name=name,
            transport=transport,
            url=url,
            created_by=created_by,
        )
        session.add(server)
        await session.flush()
        return server

    async def list_org_servers(
        self, session: AsyncSession, org_id: str
    ) -> list[MCPServerModel]:
        """列出组织 MCP Server。"""
        stmt = select(MCPServerModel).where(MCPServerModel.org_id == org_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


class MCPToolDBService(BaseDBService[MCPToolModel]):
    """MCP Tool 数据库服务。"""

    def __init__(self) -> None:
        super().__init__(MCPToolModel)

    async def create_tool(
        self,
        session: AsyncSession,
        tool_id: str,
        server_id: str,
        name: str,
        description: str = "",
        input_schema: dict | None = None,
        risk_level: str = "low",
        created_by: str = "",
    ) -> MCPToolModel:
        """注册 MCP Tool。"""
        tool = MCPToolModel(
            tool_id=tool_id,
            server_id=server_id,
            name=name,
            description=description,
            input_schema=json.dumps(input_schema or {}, ensure_ascii=False),
            risk_level=risk_level,
            created_by=created_by,
        )
        session.add(tool)
        await session.flush()
        return tool

    async def list_server_tools(
        self, session: AsyncSession, server_id: str
    ) -> list[MCPToolModel]:
        """列出 MCP Server 的工具。"""
        stmt = select(MCPToolModel).where(MCPToolModel.server_id == server_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


class AgentMCPPolicyDBService(BaseDBService[AgentMCPPolicyModel]):
    """Agent MCP 授权策略数据库服务。"""

    def __init__(self) -> None:
        super().__init__(AgentMCPPolicyModel)

    async def set_policy(
        self,
        session: AsyncSession,
        agent_id: str,
        server_id: str,
        allowed: bool = True,
    ) -> AgentMCPPolicyModel:
        """设置 MCP 授权策略。"""
        stmt = select(AgentMCPPolicyModel).where(
            AgentMCPPolicyModel.agent_id == agent_id,
            AgentMCPPolicyModel.server_id == server_id,
        )
        result = await session.execute(stmt)
        policy = result.scalar_one_or_none()

        if policy is not None:
            policy.allowed = allowed
        else:
            policy = AgentMCPPolicyModel(
                agent_id=agent_id,
                server_id=server_id,
                allowed=allowed,
            )
            session.add(policy)
        await session.flush()
        return policy


class MemoryDBService(BaseDBService[MemoryModel]):
    """Memory 记忆数据库服务。"""

    def __init__(self) -> None:
        super().__init__(MemoryModel)

    async def create_memory(
        self,
        session: AsyncSession,
        memory_id: str,
        org_id: str,
        agent_id: str,
        memory_type: str,
        content: str,
        summary: str = "",
        confidence: float = 0.5,
        source: str = "user",
    ) -> MemoryModel:
        """创建记忆。"""
        memory = MemoryModel(
            memory_id=memory_id,
            org_id=org_id,
            agent_id=agent_id,
            memory_type=memory_type,
            content=content,
            summary=summary,
            confidence=confidence,
            source=source,
        )
        session.add(memory)
        await session.flush()
        return memory

    async def list_agent_memories(
        self,
        session: AsyncSession,
        agent_id: str,
        memory_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[MemoryModel], int]:
        """列出 Agent 的记忆。"""
        filters = {"agent_id": agent_id}
        if memory_type is not None:
            filters["memory_type"] = memory_type
        return await self.list_paginated(session, offset=offset, limit=limit, **filters)


class ModelProviderDBService(BaseDBService[ModelProviderModel]):
    """模型供应商数据库服务。"""

    def __init__(self) -> None:
        super().__init__(ModelProviderModel)

    async def create_provider(
        self,
        session: AsyncSession,
        provider_id: str,
        org_id: str,
        provider_key: str,
        display_name: str,
        base_url: str,
        api_key_encrypted: str = "",
        api_key_masked: str = "",
        models: list[str] | None = None,
        default_model: str = "",
        is_enabled: bool = True,
        created_by: str = "",
    ) -> ModelProviderModel:
        """创建模型供应商配置。"""
        provider = ModelProviderModel(
            provider_id=provider_id,
            org_id=org_id,
            provider_key=provider_key,
            display_name=display_name,
            base_url=base_url,
            api_key_encrypted=api_key_encrypted,
            api_key_masked=api_key_masked,
            models_json=json.dumps(models or [], ensure_ascii=False),
            default_model=default_model,
            is_enabled=is_enabled,
            created_by=created_by,
        )
        session.add(provider)
        await session.flush()
        return provider

    async def get_by_key(
        self,
        session: AsyncSession,
        org_id: str,
        provider_key: str,
    ) -> ModelProviderModel | None:
        """根据 org_id + provider_key 查找供应商配置。"""
        stmt = select(ModelProviderModel).where(
            ModelProviderModel.org_id == org_id,
            ModelProviderModel.provider_key == provider_key,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_org_providers(
        self, session: AsyncSession, org_id: str
    ) -> list[ModelProviderModel]:
        """列出组织模型供应商。"""
        stmt = select(ModelProviderModel).where(ModelProviderModel.org_id == org_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


class BackgroundAgentDBService(BaseDBService[BackgroundAgentModel]):
    """后台 Agent 配置数据库服务。"""

    def __init__(self) -> None:
        super().__init__(BackgroundAgentModel)

    async def create_config(
        self,
        session: AsyncSession,
        config_id: str,
        org_id: str,
        agent_type: str,
        interval_seconds: int = 300,
        enabled: bool = True,
        created_by: str = "",
    ) -> BackgroundAgentModel:
        """创建后台 Agent 配置。"""
        config = BackgroundAgentModel(
            config_id=config_id,
            org_id=org_id,
            agent_type=agent_type,
            interval_seconds=interval_seconds,
            enabled=enabled,
            created_by=created_by,
        )
        session.add(config)
        await session.flush()
        return config

    async def list_org_configs(
        self, session: AsyncSession, org_id: str
    ) -> list[BackgroundAgentModel]:
        """列出组织后台 Agent 配置。"""
        stmt = select(BackgroundAgentModel).where(BackgroundAgentModel.org_id == org_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, session: AsyncSession, config_id: str, status: str
    ) -> BackgroundAgentModel:
        """更新后台 Agent 状态。"""
        config = await self.get_by_id_required(session, config_id, "config_id")
        config.status = status
        await session.flush()
        return config


# 全局数据库服务实例
skill_db = SkillDBService()
agent_skill_policy_db = AgentSkillPolicyDBService()
mcp_server_db = MCPServerDBService()
mcp_tool_db = MCPToolDBService()
agent_mcp_policy_db = AgentMCPPolicyDBService()
memory_db = MemoryDBService()
model_provider_db = ModelProviderDBService()
background_agent_db = BackgroundAgentDBService()
