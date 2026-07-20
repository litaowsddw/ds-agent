"""Deterministic registry for the runtime's genuinely executable system tools."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from packages.runtime.tools.mcp_tools import MCPTool
from packages.runtime.tools.memory_tool import MemoryRecallTool
from packages.runtime.tools.rag_tool import RAGSearchTool
from packages.runtime.tools.skill_search_tool import SkillSearchTool
from packages.runtime.tools.skill_tool import SkillCreatorTool


def build_system_tools(
    *,
    org_id: str,
    agent_id: str,
    rag_executor: Any = None,
    memory_accessor: Any = None,
    skill_search_accessor: Any = None,
    skill_creator_accessor: Any = None,
    mcp_accessor: Any = None,
    available_mcp_tools: list[dict[str, Any]] | None = None,
) -> list[BaseTool]:
    """Build the enabled, agent-scoped tool set in a stable order.

    MCP tools are included only when a policy-filtered descriptor is injected
    and their declared risk is ``low``.  Higher-risk MCP calls remain on the
    workflow approval path; this registry never weakens that boundary.
    """

    tools: list[BaseTool] = []
    if rag_executor is not None:
        tools.append(RAGSearchTool(org_id=org_id, agent_id=agent_id, rag_executor=rag_executor))
    if memory_accessor is not None:
        tools.append(MemoryRecallTool(org_id=org_id, agent_id=agent_id, memory_accessor=memory_accessor))
    if skill_search_accessor is not None:
        tools.append(SkillSearchTool(org_id=org_id, agent_id=agent_id, skill_accessor=skill_search_accessor))
    if skill_creator_accessor is not None:
        tools.append(SkillCreatorTool(org_id=org_id, agent_id=agent_id, skill_accessor=skill_creator_accessor))
    if mcp_accessor is not None:
        for tool in sorted(available_mcp_tools or [], key=lambda item: str(item.get("name") or "")):
            if str(tool.get("risk_level") or "low").lower() != "low":
                continue
            name = str(tool.get("name") or "").strip()
            if not name:
                continue
            tools.append(
                MCPTool(
                    name=name,
                    description=str(tool.get("description") or "Authorized MCP tool"),
                    org_id=org_id,
                    agent_id=agent_id,
                    mcp_accessor=mcp_accessor,
                )
            )
    return tools
