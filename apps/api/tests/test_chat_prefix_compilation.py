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
