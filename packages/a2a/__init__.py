"""A2A (Agent-to-Agent) 协议包。

提供 Agent Card 外部发现和 A2A Task 交互能力。

v0.3 升级：
- Agent Card 从数据库读取
- A2A Task 对接 Supervisor/ExecutionEngine 真正执行
- 支持 A2A Task 追加消息
"""

from packages.a2a.agent_card import AgentCard, AgentSkill, AgentCapabilities, AgentAuthentication, AgentProvider, build_agent_card
from packages.a2a.routes import router as a2a_router

__all__ = [
    "AgentCard",
    "AgentSkill",
    "AgentCapabilities",
    "AgentAuthentication",
    "AgentProvider",
    "build_agent_card",
    "a2a_router",
]
