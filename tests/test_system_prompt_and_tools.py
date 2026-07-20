"""Regression coverage for the shared platform prompt and system tool registry."""

import json

import pytest

from packages.runtime.langgraph_executor import _bounded_tool_result, _tool_call_fingerprint
from packages.runtime.system_prompt import build_agent_system_prompt, build_subagent_system_prompt
from packages.runtime.tools.registry import build_system_tools


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


def test_tool_fingerprint_is_order_stable_and_result_has_a_hard_context_cap() -> None:
    assert _tool_call_fingerprint("search", {"a": 1, "b": 2}) == _tool_call_fingerprint(
        "search", {"b": 2, "a": 1}
    )
    capped = _bounded_tool_result("x" * 20, maximum=8)
    assert capped.startswith("x" * 8)
    assert "truncated" in capped


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
