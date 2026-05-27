"""Reasonix 风格 Prompt 编译器。

该模块负责把上下文编译成 prefix-cache 友好的稳定字节序列。核心目标是：
稳定前缀不变、历史只追加、当前输入后置、临时 scratch 不进入 Prompt。
"""

import hashlib
import json
from typing import Any


class PromptContextCompiler:
    """编译 LLM Prompt 并生成 prefix hash。"""

    def compile(
        self,
        immutable_prefix: Any,
        append_only_log: Any,
        current_turn: Any,
    ) -> dict[str, object]:
        """编译 Prompt。

        参数：
            immutable_prefix: 稳定前缀，包含系统规则、Agent 配置、工具 schema。
            append_only_log: 追加式历史，不能重排。
            current_turn: 当前回合动态输入。
        """

        # prefix_text 使用稳定 JSON 序列化，确保同样内容生成完全一致的字节。
        prefix_text = self._stable_json(immutable_prefix)

        # log_text 保存追加式历史，不参与 prefix_hash，但参与完整 prompt。
        log_text = self._stable_json(append_only_log)

        # current_turn_text 保存当前动态输入，变化频率最高，应放在最后。
        current_turn_text = self._stable_json(current_turn)

        # prefix_hash 是 provider prefix-cache 观测和平台侧调试的关键指标。
        prefix_hash = hashlib.sha256(prefix_text.encode("utf-8")).hexdigest()

        # compiled_prompt 是最终发送给模型的文本表示，后续可以扩展为 messages 格式。
        compiled_prompt = "\n\n".join(
            [
                "[IMMUTABLE_PREFIX]",
                prefix_text,
                "[APPEND_ONLY_LOG]",
                log_text,
                "[CURRENT_TURN]",
                current_turn_text,
            ]
        )

        return {
            "prefix_hash": prefix_hash,
            "compiled_prompt": compiled_prompt,
            "sections": {
                "immutable_prefix": prefix_text,
                "append_only_log": log_text,
                "current_turn": current_turn_text,
            },
        }

    def _stable_json(self, value: Any) -> str:
        """把任意 JSON 兼容对象序列化为稳定字符串。"""

        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
