"""Regression coverage for the shared platform prompt and system tool registry."""

import json

import pytest

from packages.runtime.langgraph_executor import _bounded_tool_result, _tool_call_fingerprint
from packages.runtime.system_prompt import (
    build_agent_system_prompt,
    build_subagent_system_prompt,
    render_tool_catalog,
)
from packages.runtime.tools.registry import build_system_tools
from packages.runtime.tools.todo_tool import TodoWriteTool
from packages.runtime.tools.web_search_tool import WebSearchTool
from packages.runtime.tools.subagent_control_tool import ListSubagentsTool
from packages.runtime.tools.subagent_tool import SpawnSubagentTool
from packages.runtime.tools.subagent_fork_tool import SubagentForkTool


def test_agent_prompt_keeps_platform_contract_before_custom_instructions() -> None:
    prompt = build_agent_system_prompt(
        agent_name="Research agent",
        agent_description="Finds evidence",
        agent_instructions="Prefer concise Chinese answers.",
    )

    assert prompt.index("[AgentFlow platform contract]") < prompt.index("[Agent-specific instructions")
    assert "Do not invent tool calls" in prompt
    assert "Prefer concise Chinese answers." in prompt


def test_subagent_prompt_is_capability_specific_but_keeps_same_guardrails() -> None:
    prompt = build_subagent_system_prompt("SYSTEM_RAG")

    assert "[AgentFlow platform contract]" in prompt
    assert "knowledge retrieval" in prompt
    assert "Never emit fake function-call syntax" in prompt


def test_agent_prompt_sections_follow_stable_prefix_order() -> None:
    prompt = build_agent_system_prompt(
        agent_name="Support",
        tool_catalog=[{"name": "knowledge_search", "description": "Search knowledge"}],
    )

    assert prompt.index("[AgentFlow persona]") < prompt.index("[AgentFlow platform contract]")
    assert prompt.index("[AgentFlow platform contract]") < prompt.index("[Agent role]")
    assert prompt.index("[Agent role]") < prompt.index("[Available tools]")


def test_tool_catalog_is_sorted_and_advertises_only_injected_tools() -> None:
    catalog = render_tool_catalog(
        [
            {"name": "memory_recall", "description": "Recall memories"},
            {"name": "knowledge_search", "description": "Search knowledge"},
        ]
    )

    assert catalog.index("knowledge_search") < catalog.index("memory_recall")
    assert "Search knowledge" in catalog

    # An empty (or None) catalog advertises no capabilities at all.
    assert render_tool_catalog([]) == ""
    assert "[Available tools]" not in build_agent_system_prompt(agent_name="Bare")



def test_tool_fingerprint_is_order_stable_and_result_has_a_hard_context_cap() -> None:
    assert _tool_call_fingerprint("search", {"a": 1, "b": 2}) == _tool_call_fingerprint(
        "search", {"b": 2, "a": 1}
    )
    capped = _bounded_tool_result("x" * 20, maximum=8)
    assert capped.startswith("x" * 8)
    assert "truncated" in capped


def test_tool_result_pruner_keeps_head_and_tail_and_drops_the_middle() -> None:
    text = "".join(f"{i:04d}" for i in range(2000))  # 8000 chars
    pruned = _bounded_tool_result(text, maximum=1000, tail_chars=100)

    assert pruned.startswith(text[:900])
    assert pruned.endswith(text[-100:])
    assert "truncated" in pruned
    assert len(pruned) < len(text)

    # A tail larger than the threshold falls back to a plain head cap.
    capped = _bounded_tool_result("x" * 20, maximum=8, tail_chars=100)
    assert capped.startswith("x" * 8)


@pytest.mark.asyncio
async def test_direct_runtime_never_falls_back_to_a_bare_user_prompt() -> None:
    from packages.runtime.agent_runtime import AgentRuntime

    class CapturingCaller:
        last_system_prompt = ""

        async def call(self, prompt, system_prompt="", **kwargs):
            self.last_system_prompt = system_prompt
            return "done"

    caller = CapturingCaller()
    runtime = AgentRuntime(agent_id="agent_1", org_id="org_1", llm_caller=caller)
    result = await runtime.chat("hello")

    assert result["response"] == "done"
    assert "[AgentFlow platform contract]" in caller.last_system_prompt


@pytest.mark.asyncio
async def test_system_tool_registry_only_exposes_injected_and_low_risk_capabilities() -> None:
    async def rag_executor(**kwargs):
        return [{"content": "retrieved"}]

    async def memory_accessor(**kwargs):
        return [{"summary": "remembered"}]

    async def skill_search_accessor(**kwargs):
        return [{"name": "release-notes", "description": "Write release notes"}]

    async def skill_creator_accessor(**kwargs):
        return {"status": "created"}

    class MCPAccessor:
        async def get_available_tools(self, org_id, agent_id):
            return [{"name": "read_status"}]

        async def call_tool(self, **kwargs):
            return {"ok": True, "tool_name": kwargs["tool_name"]}

    tools = build_system_tools(
        org_id="org_1",
        agent_id="agent_1",
        rag_executor=rag_executor,
        memory_accessor=memory_accessor,
        skill_search_accessor=skill_search_accessor,
        skill_creator_accessor=skill_creator_accessor,
        mcp_accessor=MCPAccessor(),
        available_mcp_tools=[
            {"name": "write_external", "risk_level": "high"},
            {"name": "read_status", "description": "Read service health", "risk_level": "low"},
        ],
    )

    assert [tool.name for tool in tools] == [
        "knowledge_search",
        "memory_recall",
        "skill_search",
        "skill_create",
        "read_status",
    ]
    skill_result = json.loads(await next(tool for tool in tools if tool.name == "skill_search").ainvoke({"query": "release"}))
    assert skill_result[0]["name"] == "release-notes"
    mcp_result = json.loads(await next(tool for tool in tools if tool.name == "read_status").ainvoke({}))
    assert mcp_result == {"ok": True, "tool_name": "read_status"}


def test_system_tool_registry_gates_control_tools_on_injection() -> None:
    tools = build_system_tools(
        org_id="org_1",
        agent_id="agent_1",
        web_search_accessor=lambda **kwargs: [],
        todo_store=lambda todos: todos,
        subagent_lister=lambda: [],
    )

    assert [tool.name for tool in tools] == ["web_search", "todo_write", "list_subagents"]


@pytest.mark.asyncio
async def test_todo_write_replaces_list_and_normalizes_status() -> None:
    tool = TodoWriteTool()
    result = json.loads(await tool.ainvoke({"todos": [
        {"content": "do a", "status": "in_progress"},
        {"content": "do b", "status": "bogus"},
        {"content": "", "status": "pending"},
    ]}))

    assert result["todos"] == [
        {"content": "do a", "status": "in_progress"},
        {"content": "do b", "status": "pending"},
    ]

    replaced = json.loads(await tool.ainvoke({"todos": [{"content": "only c", "status": "completed"}]}))
    assert replaced["todos"] == [{"content": "only c", "status": "completed"}]


@pytest.mark.asyncio
async def test_web_search_uses_accessor_and_fails_honestly_without_one() -> None:
    tool = WebSearchTool()
    assert json.loads(await tool.ainvoke({"query": "x"})) == {
        "error": "Web search accessor is not configured"
    }

    async def accessor(query: str) -> dict[str, object]:
        return {"answer": "found", "sources": [{"url": "https://example.test"}]}

    result = json.loads(await WebSearchTool(web_search_accessor=accessor).ainvoke({"query": "x"}))
    assert result["answer"] == "found"


@pytest.mark.asyncio
async def test_list_subagents_returns_runtime_injected_registry() -> None:
    async def lister() -> list[dict[str, str]]:
        return [{"agent_id": "a1", "name": "Searcher", "kind": "SYSTEM_RAG"}]

    tool = ListSubagentsTool(subagent_lister=lister)
    result = json.loads(await tool.ainvoke({}))
    assert result[0]["agent_id"] == "a1"


@pytest.mark.asyncio
async def test_spawn_subagent_delegates_to_injected_executor() -> None:
    async def executor(task: str, subagent_kind: str) -> dict[str, str]:
        return {"response": f"{subagent_kind}: {task}", "status": "succeeded"}

    tool = SpawnSubagentTool(subagent_executor=executor)
    result = json.loads(await tool.ainvoke({"task": "summarize", "subagent_kind": "SYSTEM_RAG"}))
    assert result["response"] == "SYSTEM_RAG: summarize"
    assert result["status"] == "succeeded"

    assert json.loads(await SpawnSubagentTool().ainvoke({"task": "x"})) == {
        "error": "Subagent executor is not configured"
    }


@pytest.mark.asyncio
async def test_subagent_fork_delegates_to_injected_executor() -> None:
    async def executor(task: str, subagent_kind: str) -> dict[str, str]:
        return {"response": f"fork:{subagent_kind}:{task}"}

    tool = SubagentForkTool(subagent_fork_executor=executor)
    result = json.loads(await tool.ainvoke({"task": "review", "subagent_kind": "USER_SUB"}))
    assert result["response"] == "fork:USER_SUB:review"

    assert json.loads(await SubagentForkTool().ainvoke({"task": "x"})) == {
        "error": "Subagent fork executor is not configured"
    }
