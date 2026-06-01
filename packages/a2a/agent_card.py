"""A2A (Agent-to-Agent) 协议 - Agent Card 外部发现。

参考 Google A2A 协议规范，Agent Card 是 Agent 的元数据描述，
用于外部系统发现和调用 Agent。

Agent Card JSON 格式：
{
    "name": "Agent名称",
    "description": "Agent功能描述",
    "url": "https://agentflow.example.com/a2a/agent/<agent_id>",
    "version": "1.0.0",
    "capabilities": {
        "streaming": true,
        "pushNotifications": false,
        "stateTransitionHistory": true
    },
    "skills": [
        {"id": "skill_id", "name": "技能名称", "description": "技能描述"}
    ],
    "authentication": {
        "type": "bearer",
        "scheme": "bearer"
    },
    "provider": {
        "organization": "AgentFlow",
        "url": "https://agentflow.example.com"
    }
}
 """

from dataclasses import dataclass, field
from typing import Any
import json


@dataclass(slots=True)
class AgentSkill:
    """A2A Agent Skill 描述。"""
    id: str
    name: str
    description: str


@dataclass(slots=True)
class AgentCapabilities:
    """A2A Agent 能力声明。"""
    streaming: bool = True
    push_notifications: bool = False
    state_transition_history: bool = True


@dataclass(slots=True)
class AgentAuthentication:
    """A2A Agent 认证方式。"""
    type: str = "bearer"  # bearer/api_key/none
    scheme: str = "bearer"


@dataclass(slots=True)
class AgentProvider:
    """A2A Agent 提供者信息。"""
    organization: str = "AgentFlow"
    url: str = ""


@dataclass(slots=True)
class AgentCard:
    """A2A Agent Card - Agent 的元数据描述。

    用于外部系统发现和调用 Agent。
    对应 A2A 协议中的 Agent Card 规范。
    """
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)
    skills: list[AgentSkill] = field(default_factory=list)
    authentication: AgentAuthentication = field(default_factory=AgentAuthentication)
    provider: AgentProvider = field(default_factory=AgentProvider)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 A2A Agent Card JSON 格式。"""
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "capabilities": {
                "streaming": self.capabilities.streaming,
                "pushNotifications": self.capabilities.push_notifications,
                "stateTransitionHistory": self.capabilities.state_transition_history,
            },
            "skills": [
                {"id": s.id, "name": s.name, "description": s.description}
                for s in self.skills
            ],
            "authentication": {
                "type": self.authentication.type,
                "scheme": self.authentication.scheme,
            },
            "provider": {
                "organization": self.provider.organization,
                "url": self.provider.url,
            },
        }

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentCard":
        """从字典反序列化。"""
        caps_data = data.get("capabilities", {})
        skills_data = data.get("skills", [])
        auth_data = data.get("authentication", {})
        provider_data = data.get("provider", {})

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            url=data.get("url", ""),
            version=data.get("version", "1.0.0"),
            capabilities=AgentCapabilities(
                streaming=caps_data.get("streaming", True),
                push_notifications=caps_data.get("pushNotifications", False),
                state_transition_history=caps_data.get("stateTransitionHistory", True),
            ),
            skills=[
                AgentSkill(id=s.get("id", ""), name=s.get("name", ""), description=s.get("description", ""))
                for s in skills_data
            ],
            authentication=AgentAuthentication(
                type=auth_data.get("type", "bearer"),
                scheme=auth_data.get("scheme", "bearer"),
            ),
            provider=AgentProvider(
                organization=provider_data.get("organization", "AgentFlow"),
                url=provider_data.get("url", ""),
            ),
        )


def build_agent_card(
    agent_id: str,
    name: str,
    description: str,
    base_url: str = "http://localhost:8000",
    skills: list[dict[str, str]] | None = None,
) -> AgentCard:
    """根据 Agent 信息构建 Agent Card。"""
    skill_list = [
        AgentSkill(id=s.get("id", ""), name=s.get("name", ""), description=s.get("description", ""))
        for s in (skills or [])
    ]

    return AgentCard(
        name=name,
        description=description,
        url=f"{base_url}/a2a/agents/{agent_id}",
        skills=skill_list,
    )
