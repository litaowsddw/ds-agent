from types import SimpleNamespace

from app.routes.chat import _compile_agent_chat_prompt
from app.services.context_tokens import preflight_chat_context


def test_deepseek_preflight_uses_official_tokenizer_for_final_prompt() -> None:
    compiled = _compile_agent_chat_prompt(
        SimpleNamespace(
            name="Support",
            description="Answers questions",
            system_prompt="Be accurate.",
        ),
        "Explain prefix cache.",
        skill_catalog="search: Search documentation",
    )

    result = preflight_chat_context(
        provider="deepseek",
        model="deepseek-v4-pro",
        compiled_prompt=str(compiled["compiled_prompt"]),
        components=compiled["context_breakdown"],
    )

    assert result.status == "official_tokenizer"
    assert result.tokenizer == "deepseek-v3-official"
    assert result.input_tokens is not None and result.input_tokens > 0
    assert result.stable_prefix_tokens is not None and result.stable_prefix_tokens > 0
    assert sum(int(item["tokens"]) for item in result.breakdown) == result.input_tokens
    assert any(item["key"] == "current_user" for item in result.breakdown)


def test_unknown_model_uses_explicit_characters_divided_by_four_estimate() -> None:
    result = preflight_chat_context(
        provider="custom-openai-compatible",
        model="unknown-model",
        compiled_prompt="x" * 100,
        components=[],
    )

    assert result.status == "characters_divided_by_4"
    assert result.input_tokens == 25
    assert sum(int(item["tokens"]) for item in result.breakdown) == result.input_tokens
