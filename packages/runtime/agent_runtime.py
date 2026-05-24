"""Agent Runtime 核心对象。

AgentRuntime 是每个 Agent 的运行时门面，后续 API、Workflow Worker、后台 Agent
都应该通过它访问上下文、Skill、MCP、Memory 等能力。
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentRuntime:
    """描述一个 Agent 的运行时边界。"""

    # agent_id 是 Agent 的唯一标识，用于隔离 Workspace、Session、Skill、Memory。
    agent_id: str

    # org_id 是组织标识，是多租户隔离的第一层边界。
    org_id: str

    # enabled_capabilities 表示当前运行时启用的能力，MVP 阶段用于接口自描述。
    enabled_capabilities: list[str] = field(
        default_factory=lambda: [
            "workspace",
            "session",
            "context",
            "skill",
            "mcp",
            "memory",
            "prompt_compiler",
            "background_agent",
        ]
    )

    def describe(self) -> dict[str, object]:
        """返回 Agent Runtime 的能力描述。"""

        # runtime_scope 是运行时隔离范围，后续权限系统会围绕它做资源校验。
        runtime_scope = {
            "org_id": self.org_id,
            "agent_id": self.agent_id,
        }

        return {
            "runtime_scope": runtime_scope,
            "enabled_capabilities": self.enabled_capabilities,
        }

