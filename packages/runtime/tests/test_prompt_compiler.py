"""PromptContextCompiler 测试。"""

from packages.runtime.prompt_compiler import PromptContextCompiler


def test_prefix_hash_is_stable_for_same_prefix() -> None:
    """相同稳定前缀即使字段顺序不同，也应生成相同 prefix hash。"""

    # compiler 是被测 Prompt 编译器。
    compiler = PromptContextCompiler()

    # first_prefix 和 second_prefix 内容相同但字段顺序不同，用于验证稳定序列化。
    first_prefix = {"tools": [{"name": "search"}], "system": "stable"}
    second_prefix = {"system": "stable", "tools": [{"name": "search"}]}

    first_result = compiler.compile(
        immutable_prefix=first_prefix,
        append_only_log=[],
        current_turn={"input": "hello"},
    )
    second_result = compiler.compile(
        immutable_prefix=second_prefix,
        append_only_log=[],
        current_turn={"input": "hello"},
    )

    assert first_result["prefix_hash"] == second_result["prefix_hash"]
