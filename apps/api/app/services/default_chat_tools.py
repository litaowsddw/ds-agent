"""Supervisor 默认系统工具集（opencode 风格注册）。

给每个 Supervisor 会话装配"安全读路径"工具：知识检索、记忆召回、
技能检索与 Agent Workspace 文件读取。高风险 MCP 工具仍走 Workflow 审批路径。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.db.agent_db import workspace_db
from app.services.db.runtime_db import skill_db
from app.services.db.workflow_db import knowledge_base_db
from app.services.knowledge_vector_index import (
    build_embedding_provider_from_env,
    build_vector_index_from_env,
)
from app.services.memory_vector import memory_vector_service


def build_supervisor_tools(
    db: AsyncSession,
    *,
    org_id: str,
    agent_id: str,
    subagent_lister: Any = None,
    subagent_executor: Any = None,
    subagent_fork_executor: Any = None,
) -> list[BaseTool]:
    """装配 Supervisor 子代理可用的默认工具。

    除安全读路径（知识检索/记忆/技能/工作区读取）外，当运行时注入了
    subagent_lister/subagent_executor 时，还会装配 DSH 式的子代理控制工具
    （list_subagents / spawn_subagent / subagent_fork），让 Agent 能动态委派
    写作/审稿等独立子任务。
    """

    async def rag_executor(query: str, collection: str = "default", top_k: int = 5, **_: Any) -> list[dict[str, Any]]:
        provider = build_embedding_provider_from_env()
        index = build_vector_index_from_env(embedding_dimension=provider.dimension)
        query_embedding = (await asyncio.to_thread(provider.embed_texts, [query]))[0]
        if collection and collection != "default":
            kb_ids = [str(collection)]
        else:
            kbs, _ = await knowledge_base_db.list_org_kbs(db, org_id)
            kb_ids = [str(kb.kb_id) for kb in kbs]
        hits: list[tuple[str, float, str]] = []
        for kb_id in kb_ids:
            for hit in index.search(org_id=org_id, kb_id=kb_id, query_embedding=query_embedding, limit=top_k):
                hits.append((kb_id, hit.score, hit.chunk_id))
        hits.sort(key=lambda item: item[1], reverse=True)
        return [
            {"kb_id": kb_id, "chunk_id": chunk_id, "score": score}
            for kb_id, score, chunk_id in hits[:top_k]
        ]

    async def memory_accessor(query: str, org_id: str, agent_id: str, top_k: int = 5, **_: Any) -> list[dict[str, Any]]:
        memories = await memory_vector_service.recall(
            db, org_id=org_id, agent_id=agent_id, query=query, limit=top_k
        )
        return [
            {
                key: getattr(memory, key)
                for key in ("memory_id", "memory_type", "content", "summary", "confidence")
                if hasattr(memory, key)
            }
            for memory in memories
        ]

    async def knowledge_list_accessor(org_id: str, **_: Any) -> list[dict[str, Any]]:
        kbs, _ = await knowledge_base_db.list_org_kbs(db, org_id)
        return [
            {
                "kb_id": kb.kb_id,
                "name": kb.name,
                "description": str(getattr(kb, "description", "") or ""),
            }
            for kb in kbs
        ]

    async def skill_search_accessor(query: str, org_id: str, agent_id: str, top_k: int = 5, **_: Any) -> list[dict[str, Any]]:
        allowed = await skill_db.list_agent_allowed_skills(db, agent_id=agent_id, org_id=org_id)
        needle = query.strip().lower()
        matched = [
            skill for skill in allowed
            if not needle or needle in f"{skill.name} {skill.description}".lower()
        ]
        return [
            {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "description": skill.description,
                "scope": str(getattr(skill, "scope", "")),
            }
            for skill in matched[:top_k]
        ]

    async def workspace_reader(query: str, org_id: str, agent_id: str, **_: Any) -> dict[str, str]:
        try:
            ws = await workspace_db.get_by_agent_id_required(db, agent_id)
        except ValueError:
            return {"error": "Agent 没有配置 Workspace"}
        files = {
            "AGENTS.md": ws.agents_md or "",
            "SOUL.md": ws.soul_md or "",
            "TOOLS.md": ws.tools_md or "",
            "MEMORY.md": ws.memory_md or "",
        }
        needle = (query or "").strip().upper()
        if needle in files:
            return {needle: files[needle]}
        for name, content in files.items():
            if needle and needle in name:
                return {name: content}
        return {name: content for name, content in files.items() if content}

    class WorkspaceReadTool(BaseTool):
        name: str = "workspace_read"
        description: str = (
            "读取当前 Agent 的 Workspace 配置（AGENTS.md/SOUL.md/TOOLS.md/MEMORY.md）。"
            "需要确认当前 Agent 的身份定义、工具约定或组织规则时使用；不要凭记忆描述。"
        )

        async def _arun(self, query: str = "", **kwargs: Any) -> str:
            result = await workspace_reader(str(query or ""), "", "")
            return json.dumps(result, ensure_ascii=False)

        def _run(self, query: str = "", **kwargs: Any) -> str:
            # langchain BaseTool 要求同步实现存在；执行器只走 _arun。
            raise NotImplementedError("workspace_read 仅支持异步调用")

    from packages.runtime.tools.registry import build_system_tools

    tools = build_system_tools(
        org_id=org_id,
        agent_id=agent_id,
        knowledge_list_accessor=knowledge_list_accessor,
        rag_executor=rag_executor,
        memory_accessor=memory_accessor,
        skill_search_accessor=skill_search_accessor,
        subagent_lister=subagent_lister,
        subagent_executor=subagent_executor,
        subagent_fork_executor=subagent_fork_executor,
    )
    tools.append(WorkspaceReadTool())
    return tools
