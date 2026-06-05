from types import SimpleNamespace

from apps.api.app.services.hermes_memory import (
    build_memory_extraction_candidate,
    build_three_layer_memory_context,
    format_recent_messages,
)


def test_three_layer_memory_context_formats_layers() -> None:
    messages = [
        SimpleNamespace(sequence=1, role="user", content="请记住我偏好中文", estimated_tokens=6),
        SimpleNamespace(sequence=2, role="assistant", content="已记录。", estimated_tokens=2),
    ]
    memories = [
        SimpleNamespace(
            memory_type="preference",
            summary="用户偏好中文回答",
            content="用户偏好中文回答",
            confidence=0.85,
        )
    ]

    context = build_three_layer_memory_context(
        recent_messages=messages,
        compact_summary="用户正在配置 AgentFlow。",
        memories=memories,
        token_threshold=20,
    )

    assert "Hermes Memory Layer 1" in context.prompt_context
    assert "请记住我偏好中文" in context.prompt_context
    assert "用户正在配置 AgentFlow" in context.prompt_context
    assert "用户偏好中文回答" in context.prompt_context


def test_memory_candidate_is_conservative() -> None:
    assert build_memory_extraction_candidate("你好") is None

    candidate = build_memory_extraction_candidate("请记住，以后默认用中文回答")

    assert candidate is not None
    memory_type, content = candidate
    assert memory_type == "rule"
    assert "默认用中文" in content


def test_recent_messages_are_sequence_ordered() -> None:
    messages = [
        SimpleNamespace(sequence=2, role="assistant", content="B"),
        SimpleNamespace(sequence=1, role="user", content="A"),
    ]

    formatted = format_recent_messages(messages)

    assert formatted.splitlines() == ["1. user: A", "2. assistant: B"]
