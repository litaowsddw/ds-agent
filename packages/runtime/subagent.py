"""SubAgent 管理 - 用户 SubAgent 和系统 SubAgent。

SubAgent 类型：
- USER_SUB: 用户自定义 Agent
- SYSTEM_SKILL: Skill Creator SubAgent（根据用户描述生成 SKILL.md）
- SYSTEM_RAG: Knowledge Search SubAgent（知识库检索）
- SYSTEM_TOOL: System Tool SubAgent（系统级工具调用）
 """

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentKind(StrEnum):
    """Agent 类型枚举。"""
    SUPERVISOR = "SUPERVISOR"
    USER_SUB = "USER_SUB"
    SYSTEM_SKILL = "SYSTEM_SKILL"
    SYSTEM_RAG = "SYSTEM_RAG"
    SYSTEM_TOOL = "SYSTEM_TOOL"


@dataclass(slots=True)
class SubAgentConfig:
    """SubAgent 配置。"""
    # agent_id 是 SubAgent 唯一标识
    agent_id: str
    # org_id 是所属组织
    org_id: str
    # kind 是 SubAgent 类型
    kind: AgentKind
    # name 是展示名称
    name: str
    # description 是功能描述
    description: str
    # model_provider 是使用的模型供应商
    model_provider: str = "mock"
    # model_name 是使用的模型名称
    model_name: str = "mock-model"
    # system_prompt 是系统提示词
    system_prompt: str = ""
    # workspace_id 是所属 Workspace
    workspace_id: str = ""
    # enabled 是否启用
    enabled: bool = True


class SubAgentRegistry:
    """SubAgent 注册表。

    管理一个 Workspace 内的所有 SubAgent 配置。
    """

    def __init__(self) -> None:
        self._subagents: dict[str, SubAgentConfig] = {}

    def register(self, config: SubAgentConfig) -> None:
        """注册一个 SubAgent。"""
        self._subagents[config.agent_id] = config

    def unregister(self, agent_id: str) -> None:
        """注销一个 SubAgent。"""
        self._subagents.pop(agent_id, None)

    def get(self, agent_id: str) -> SubAgentConfig | None:
        """获取 SubAgent 配置。"""
        return self._subagents.get(agent_id)

    def list_by_kind(self, kind: AgentKind) -> list[SubAgentConfig]:
        """按类型列出 SubAgent。"""
        return [s for s in self._subagents.values() if s.kind == kind and s.enabled]

    def list_all(self, enabled_only: bool = True) -> list[SubAgentConfig]:
        """列出所有 SubAgent。"""
        if enabled_only:
            return [s for s in self._subagents.values() if s.enabled]
        return list(self._subagents.values())

    def list_available_for_supervisor(self) -> list[dict[str, Any]]:
        """列出 Supervisor 可调用的 SubAgent 摘要。"""
        return [
            {
                "agent_id": s.agent_id,
                "name": s.name,
                "description": s.description,
                "kind": s.kind,
                "model_provider": s.model_provider,
                "model_name": s.model_name,
            }
            for s in self._subagents.values()
            if s.enabled and s.kind != AgentKind.SUPERVISOR
        ]


def create_system_subagents(org_id: str, workspace_id: str) -> list[SubAgentConfig]:
    """创建系统级 SubAgent 配置。

    每个新 Workspace 创建时自动注册以下系统 SubAgent：
    - Skill Creator: 根据用户描述生成 SKILL.md
    - Knowledge Search: 知识库检索
    - System Tool: 系统级工具
    """
    return [
        SubAgentConfig(
            agent_id=f"sys_skill_{org_id[:8]}",
            org_id=org_id,
            kind=AgentKind.SYSTEM_SKILL,
            name="Skill Creator",
            description="根据用户描述生成 SKILL.md 技能文件，支持自动检测和手动触发。",
            model_provider="mock",
            model_name="mock-model",
            system_prompt="你是一个 Skill Creator。根据用户描述，生成标准格式的 SKILL.md 文件。SKILL.md 包含 YAML front matter（name, description, trigger_conditions）和 Markdown 正文（步骤、示例、注意事项）。",
            workspace_id=workspace_id,
        ),
        SubAgentConfig(
            agent_id=f"sys_rag_{org_id[:8]}",
            org_id=org_id,
            kind=AgentKind.SYSTEM_RAG,
            name="Knowledge Search",
            description="在知识库中检索相关文档和片段，返回最匹配的内容。",
            model_provider="mock",
            model_name="mock-model",
            system_prompt="你是一个知识检索助手。根据用户查询，从知识库中检索最相关的文档片段，并返回结构化的检索结果。",
            workspace_id=workspace_id,
        ),
        SubAgentConfig(
            agent_id=f"sys_tool_{org_id[:8]}",
            org_id=org_id,
            kind=AgentKind.SYSTEM_TOOL,
            name="System Tool",
            description="执行系统级工具操作，如文件管理、API 调用等。",
            model_provider="mock",
            model_name="mock-model",
            system_prompt="你是一个系统工具助手。根据用户请求，调用相应的系统工具完成任务。",
            workspace_id=workspace_id,
        ),
    ]
