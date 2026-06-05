"""上下文管理引擎。

ContextEngine 参考 OpenClaw 的 ingest / assemble / compact / after_turn 生命周期。
MVP 阶段先提供结构化上下文组装能力，后续接入数据库、向量召回和自动压缩。
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class ContextSection:
    """上下文片段。"""

    # name 表示上下文片段名称，例如 system、agent、memory、current_input。
    name: str

    # content 表示上下文片段内容，MVP 阶段使用字符串，后续可扩展为富结构。
    content: str

    # estimated_tokens 表示估算 token 数，用于预算控制和前端 Context Inspector。
    estimated_tokens: int


class ContextEngine:
    """负责 Agent 上下文的进入、组装、压缩和回合后处理。"""

    def ingest(self, session_id: str, message: str) -> dict[str, str]:
        """接收一条新消息。

        参数：
            session_id: 会话标识。
            message: 用户或系统写入的消息。
        """

        return {"session_id": session_id, "status": "received", "message": message}

    def assemble(self, user_input: str, token_budget: int) -> dict[str, object]:
        """组装一次模型调用上下文。"""

        # system_section 是稳定系统上下文，后续会包含平台策略和安全边界。
        system_section = ContextSection(
            name="system",
            content="你是 AgentFlow 中受组织权限和运行时策略约束的 Agent。",
            estimated_tokens=32,
        )

        # agent_section 是 Agent 级上下文，后续来自 Workspace 中的 AGENTS.md / SOUL.md。
        agent_section = ContextSection(
            name="agent",
            content="当前 Agent 未传入 Workspace 上下文。",
            estimated_tokens=16,
        )

        # current_input_section 是当前回合动态输入，应位于上下文尾部以提高 prefix cache 命中率。
        current_input_section = ContextSection(
            name="current_input",
            content=user_input,
            estimated_tokens=max(1, len(user_input) // 4),
        )

        sections = [system_section, agent_section, current_input_section]

        # total_estimated_tokens 是本次上下文总预算消耗，用于判断是否需要压缩或截断。
        total_estimated_tokens = sum(section.estimated_tokens for section in sections)

        return {
            "token_budget": token_budget,
            "total_estimated_tokens": total_estimated_tokens,
            "need_compaction": total_estimated_tokens > token_budget,
            "sections": [asdict(section) for section in sections],
        }

    def assemble_from_session(
        self,
        workspace_files: dict[str, str],
        compact_summary: str,
        messages: list[dict[str, Any]],
        current_input: str,
        token_budget: int,
        skill_summaries: list[dict[str, str]] | None = None,
        memories: list[dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        """从 Agent Workspace 和 Session 历史组装上下文。

        参数：
            workspace_files: Agent Workspace 文件内容，包含 AGENTS.md、SOUL.md 等。
            compact_summary: 历史压缩摘要。
            messages: append-only 会话消息。
            current_input: 当前回合输入。
            token_budget: 本次上下文 token 预算。
            skill_summaries: 可用 Skill 摘要，只包含名称和描述，不包含完整 SKILL.md。
            memories: 召回的长期记忆摘要。
        """

        # stable_workspace_text 是 Agent 稳定上下文，应该尽量保持顺序和内容稳定。
        stable_workspace_text = self._join_workspace_files(workspace_files)

        # compact_section_text 是压缩摘要，避免无限增长的历史拖垮上下文窗口。
        compact_section_text = compact_summary or "暂无压缩摘要。"

        # recent_messages_text 是最近未压缩消息，保持 append-only 顺序。
        recent_messages_text = self._format_messages(messages)

        # skill_summary_text 是可用 Skill 摘要，避免把完整 Skill 指令塞进上下文。
        skill_summary_text = self._format_skill_summaries(skill_summaries or [])

        # memory_text 是长期记忆摘要，按召回顺序注入。
        memory_text = self._format_memories(memories or [])

        sections = [
            ContextSection(
                name="workspace",
                content=stable_workspace_text,
                estimated_tokens=self._estimate_tokens(stable_workspace_text),
            ),
            ContextSection(
                name="skill_summaries",
                content=skill_summary_text,
                estimated_tokens=self._estimate_tokens(skill_summary_text),
            ),
            ContextSection(
                name="memories",
                content=memory_text,
                estimated_tokens=self._estimate_tokens(memory_text),
            ),
            ContextSection(
                name="compact_summary",
                content=compact_section_text,
                estimated_tokens=self._estimate_tokens(compact_section_text),
            ),
            ContextSection(
                name="append_only_messages",
                content=recent_messages_text,
                estimated_tokens=self._estimate_tokens(recent_messages_text),
            ),
            ContextSection(
                name="current_input",
                content=current_input,
                estimated_tokens=self._estimate_tokens(current_input),
            ),
        ]

        total_estimated_tokens = sum(section.estimated_tokens for section in sections)

        return {
            "token_budget": token_budget,
            "total_estimated_tokens": total_estimated_tokens,
            "need_compaction": total_estimated_tokens > token_budget,
            "sections": [asdict(section) for section in sections],
        }

    def compact(self, session_id: str, force: bool = False) -> dict[str, object]:
        """压缩指定会话历史。"""

        # force 表示是否忽略 token 阈值强制压缩。
        should_force = force

        return {"session_id": session_id, "status": "compacted", "force": should_force}

    def after_turn(self, session_id: str, run_result: dict[str, object]) -> dict[str, object]:
        """模型回合结束后的清理和记忆写入入口。"""

        # run_result 保存本轮执行结果，后续会用于提取长期记忆和更新摘要。
        final_run_result = run_result

        return {"session_id": session_id, "status": "processed", "run_result": final_run_result}

    def _join_workspace_files(self, workspace_files: dict[str, str]) -> str:
        """按稳定顺序拼接 Workspace 文件。"""

        # stable_order 是 Reasonix prefix-cache 友好设计中的固定前缀顺序。
        stable_order = ["AGENTS.md", "SOUL.md", "TOOLS.md", "MEMORY.md"]

        # sections 保存拼接后的文件片段。
        sections: list[str] = []
        for file_name in stable_order:
            file_content = workspace_files.get(file_name, "")
            sections.append(f"[{file_name}]\n{file_content}")

        return "\n\n".join(sections)

    def _format_messages(self, messages: list[dict[str, Any]]) -> str:
        """把 append-only 消息格式化为稳定文本。"""

        # sorted_messages 按 sequence 排序，防止调用方传入乱序消息影响 prefix 稳定性。
        sorted_messages = sorted(messages, key=lambda message: int(message.get("sequence", 0)))

        lines: list[str] = []
        for message in sorted_messages:
            role = str(message.get("role", "unknown"))
            content = str(message.get("content", ""))
            sequence = int(message.get("sequence", 0))
            lines.append(f"{sequence}. {role}: {content}")

        return "\n".join(lines)

    def _format_skill_summaries(self, skill_summaries: list[dict[str, str]]) -> str:
        """格式化 Skill 摘要。"""

        if not skill_summaries:
            return "暂无可用 Skill。"

        # sorted_summaries 按 name 排序，保证注入顺序稳定。
        sorted_summaries = sorted(skill_summaries, key=lambda skill: skill.get("name", ""))

        lines: list[str] = []
        for skill in sorted_summaries:
            name = skill.get("name", "")
            description = skill.get("description", "")
            scope = skill.get("scope", "")
            lines.append(f"- {name} [{scope}]: {description}")

        return "\n".join(lines)

    def _format_memories(self, memories: list[dict[str, Any]]) -> str:
        """格式化长期记忆摘要。"""

        if not memories:
            return "暂无召回记忆。"

        lines: list[str] = []
        for memory in memories:
            memory_type = str(memory.get("memory_type", "memory"))
            summary = str(memory.get("summary", ""))
            confidence = memory.get("confidence", "")
            lines.append(f"- [{memory_type}] {summary} (confidence={confidence})")

        return "\n".join(lines)

    def _estimate_tokens(self, content: str) -> int:
        """粗略估算 token 数。"""

        return max(1, len(content) // 4)
