from types import SimpleNamespace

from app.routes.chat import _compile_agent_chat_prompt


def test_agent_chat_prefix_is_stable_across_messages_and_memory() -> None:
    agent = SimpleNamespace(
        name="Support Agent",
        description="Answers product questions",
        system_prompt="Be concise and accurate.",
    )

    first = _compile_agent_chat_prompt(
        agent,
        "How do I configure it?",
        memory_context="User previously selected model A.",
        skill_catalog="search: Search the knowledge base",
    )
    second = _compile_agent_chat_prompt(
        agent,
        "What about model B?",
        memory_context="User previously selected model B.",
        skill_catalog="search: Search the knowledge base",
    )

    assert first["prefix_hash"] == second["prefix_hash"]
    assert "How do I configure it?" in str(first["compiled_prompt"])
    assert "User previously selected model B." in str(second["compiled_prompt"])
    assert first["messages"][-1] == {"role": "user", "content": "How do I configure it?"}
    assert all("content" in item for item in first["context_breakdown"])


def test_compacted_session_summary_precedes_recent_native_messages() -> None:
    agent = SimpleNamespace(name="Support", description="", system_prompt="Be accurate.")
    recent = [
        SimpleNamespace(sequence=11, role="user", content="Keep the deployment private."),
        SimpleNamespace(sequence=12, role="assistant", content="I will use the internal endpoint."),
    ]

    compiled = _compile_agent_chat_prompt(
        agent,
        "What remains?",
        recent_messages=recent,
        compact_summary="Deployment target is the internal environment.",
        long_term_context="User prefers concise Chinese answers.",
    )

    messages = compiled["messages"]
    contents = [item["content"] for item in messages]
    assert contents.index("[Session compaction summary]\nDeployment target is the internal environment.") < contents.index("Keep the deployment private.")
    assert contents.index("I will use the internal endpoint.") < contents.index("[Relevant long-term memory; use only when applicable]\nUser prefers concise Chinese answers.")
    assert messages[-1] == {"role": "user", "content": "What remains?"}


def test_agent_chat_prefix_changes_when_agent_instructions_change() -> None:
    first = _compile_agent_chat_prompt(
        SimpleNamespace(name="Agent", description="", system_prompt="Answer briefly."),
        "Hello",
    )
    second = _compile_agent_chat_prompt(
        SimpleNamespace(name="Agent", description="", system_prompt="Answer with details."),
        "Hello",
    )

    assert first["prefix_hash"] != second["prefix_hash"]


def test_agent_chat_prefix_includes_platform_contract_and_capability_boundary() -> None:
    compiled = _compile_agent_chat_prompt(
        SimpleNamespace(name="Support", description="Product help", system_prompt="Be concise."),
        "How do I configure it?",
    )

    system_prompt = compiled["messages"][0]["content"]
    capability_boundary = compiled["messages"][1]["content"]
    assert "[AgentFlow platform contract]" in system_prompt
    assert "Do not invent tool calls" in system_prompt
    assert "Only tools supplied through structured schemas are executable" in capability_boundary
