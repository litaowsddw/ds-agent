"""Deterministic registry for the runtime's genuinely executable system tools."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from packages.runtime.tools.mcp_tools import MCPTool
from packages.runtime.tools.memory_tool import MemoryRecallTool
from packages.runtime.tools.rag_tool import RAGSearchTool
from packages.runtime.tools.skill_search_tool import SkillSearchTool
from packages.runtime.tools.skill_tool import SkillCreatorTool
from packages.runtime.tools.knowledge_list_tool import KnowledgeListTool
from packages.runtime.tools.web_search_tool import WebSearchTool
from packages.runtime.tools.todo_tool import TodoWriteTool
from packages.runtime.tools.subagent_control_tool import ListSubagentsTool
from packages.runtime.tools.goal_tool import CreateGoalTool, GetGoalTool, UpdateGoalTool
from packages.runtime.tools.plan_mode_tool import ExitPlanModeTool
from packages.runtime.tools.subagent_tool import SpawnSubagentTool
from packages.runtime.tools.fs_tool import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    GlobTool,
    GrepTool,
)
from packages.runtime.tools.ask_user_tool import AskUserTool
from packages.runtime.tools.jobs_tool import ListJobsTool, ReadJobOutputTool, KillJobTool
from packages.runtime.tools.shell_tool import ShellTool
from packages.runtime.tools.ralph_tool import RalphTool
from packages.runtime.tools.workflow_tool import WorkflowTool
from packages.runtime.tools.subagent_fork_tool import SubagentForkTool
from packages.runtime.permissions import SandboxMode, allows, permission_for


def build_system_tools(
    *,
    org_id: str,
    agent_id: str,
    rag_executor: Any = None,
    memory_accessor: Any = None,
    skill_search_accessor: Any = None,
    skill_creator_accessor: Any = None,
    knowledge_list_accessor: Any = None,
    web_search_accessor: Any = None,
    todo_store: Any = None,
    subagent_lister: Any = None,
    subagent_executor: Any = None,
    subagent_fork_executor: Any = None,
    goal_manager: Any = None,
    plan_mode_manager: Any = None,
    filesystem: Any = None,
    ask_user_accessor: Any = None,
    job_registry: Any = None,
    shell_executor: Any = None,
    ralph_runner: Any = None,
    workflow_runner: Any = None,
    sandbox_mode: SandboxMode | str = SandboxMode.DANGER_FULL_ACCESS,
    mcp_accessor: Any = None,
    available_mcp_tools: list[dict[str, Any]] | None = None,
) -> list[BaseTool]:
    """Build the enabled, agent-scoped tool set in a stable order.

    MCP tools are included only when a policy-filtered descriptor is injected
    and their declared risk is ``low``.  Higher-risk MCP calls remain on the
    workflow approval path; this registry never weakens that boundary.

    Control/information/fs/jobs/shell tools are added only when their backing
    accessor/manager is injected, and the final catalog is then filtered by the
    granted ``sandbox_mode`` so a read-only agent never sees a mutating tool.
    """

    tools: list[BaseTool] = []
    if knowledge_list_accessor is not None:
        tools.append(KnowledgeListTool(org_id=org_id, agent_id=agent_id, knowledge_list_accessor=knowledge_list_accessor))
    if rag_executor is not None:
        tools.append(RAGSearchTool(org_id=org_id, agent_id=agent_id, rag_executor=rag_executor))
    if memory_accessor is not None:
        tools.append(MemoryRecallTool(org_id=org_id, agent_id=agent_id, memory_accessor=memory_accessor))
    if skill_search_accessor is not None:
        tools.append(SkillSearchTool(org_id=org_id, agent_id=agent_id, skill_accessor=skill_search_accessor))
    if skill_creator_accessor is not None:
        tools.append(SkillCreatorTool(org_id=org_id, agent_id=agent_id, skill_accessor=skill_creator_accessor))
    if web_search_accessor is not None:
        tools.append(WebSearchTool(web_search_accessor=web_search_accessor))
    if todo_store is not None:
        tools.append(TodoWriteTool(todo_store=todo_store))
    if subagent_lister is not None:
        tools.append(ListSubagentsTool(subagent_lister=subagent_lister))
    if subagent_executor is not None:
        tools.append(SpawnSubagentTool(subagent_executor=subagent_executor))
    if subagent_fork_executor is not None:
        tools.append(SubagentForkTool(subagent_fork_executor=subagent_fork_executor))
    if goal_manager is not None:
        tools.append(CreateGoalTool(goal_manager=goal_manager))
        tools.append(GetGoalTool(goal_manager=goal_manager))
        tools.append(UpdateGoalTool(goal_manager=goal_manager))
    if plan_mode_manager is not None:
        tools.append(ExitPlanModeTool(plan_mode_manager=plan_mode_manager))
    if filesystem is not None:
        tools.append(ReadFileTool(filesystem=filesystem))
        tools.append(WriteFileTool(filesystem=filesystem))
        tools.append(EditFileTool(filesystem=filesystem))
        tools.append(GlobTool(filesystem=filesystem))
        tools.append(GrepTool(filesystem=filesystem))
    if ask_user_accessor is not None:
        tools.append(AskUserTool(ask_user_accessor=ask_user_accessor))
    if job_registry is not None:
        tools.append(ListJobsTool(job_registry=job_registry))
        tools.append(ReadJobOutputTool(job_registry=job_registry))
        tools.append(KillJobTool(job_registry=job_registry))
    if shell_executor is not None:
        tools.append(ShellTool(shell_executor=shell_executor))
    if ralph_runner is not None:
        tools.append(RalphTool(ralph_runner=ralph_runner))
    if workflow_runner is not None:
        tools.append(WorkflowTool(workflow_runner=workflow_runner))
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
    mode = SandboxMode(str(sandbox_mode))
    return [tool for tool in tools if allows(mode, permission_for(tool.name))]
