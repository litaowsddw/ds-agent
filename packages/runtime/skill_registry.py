"""Skill 注册表。

Skill 借鉴 OpenClaw 的 `SKILL.md` 组织方式。MVP 阶段先定义数据结构和解析入口，
后续接入数据库、Marketplace、Agent allowlist 和文件 watcher。
"""

from dataclasses import dataclass


@dataclass(slots=True)
class SkillSummary:
    """Skill 摘要。

    默认注入模型上下文时只暴露摘要，不直接暴露完整 SKILL.md 内容。
    """

    # name 是 Skill 唯一名称。
    name: str

    # description 是 Skill 触发条件和能力摘要。
    description: str

    # scope 表示 Skill 来源层级，例如 bundled、org、team、agent。
    scope: str


class SkillRegistry:
    """负责加载和筛选 Agent 可用 Skill。"""

    def list_allowed_skills(self, agent_id: str, org_id: str) -> list[SkillSummary]:
        """返回指定 Agent 可用的 Skill 摘要列表。"""

        # agent_id 和 org_id 后续会用于查询 allowlist 和隔离策略。
        _agent_id = agent_id
        _org_id = org_id

        return [
            SkillSummary(
                name="workflow-builder",
                description="用于创建、校验和解释 AgentFlow 工作流。",
                scope="bundled",
            )
        ]

