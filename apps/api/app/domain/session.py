"""Agent Session 与消息领域模型。

Session 是 Agent 长期运行时的会话边界。它和 Workflow Run 不同：
Workflow Run 更偏一次任务执行，Session 更偏连续对话、上下文、记忆和后台 Agent 维护。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from apps.api.app.domain.identity import utc_now


class SessionQueueMode(StrEnum):
    """会话忙碌时的新消息处理模式。"""

    QUEUE = "queue"
    COLLECT = "collect"


class SessionStatus(StrEnum):
    """会话状态。"""

    IDLE = "idle"
    RUNNING = "running"
    CLOSED = "closed"


class MessageRole(StrEnum):
    """会话消息角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass(slots=True)
class AgentSession:
    """Agent 会话实体。"""

    # session_id 是会话唯一标识。
    session_id: str

    # org_id 是会话所属组织，必须与 Agent 的 org_id 一致。
    org_id: str

    # agent_id 是会话所属 Agent。
    agent_id: str

    # user_id 是会话发起用户。
    user_id: str

    # queue_mode 表示 Agent 忙碌时新消息如何处理。
    queue_mode: SessionQueueMode

    # status 表示当前会话状态。
    status: SessionStatus = SessionStatus.IDLE

    # compact_summary 保存压缩后的历史摘要，原始消息仍然 append-only 保留。
    compact_summary: str = ""

    # created_at 是会话创建时间。
    created_at: datetime = field(default_factory=utc_now)

    # updated_at 是会话最后更新时间。
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class SessionMessage:
    """会话消息实体。"""

    # message_id 是消息唯一标识。
    message_id: str

    # session_id 是消息所属会话。
    session_id: str

    # org_id 是消息所属组织，用于审计和隔离。
    org_id: str

    # agent_id 是消息所属 Agent。
    agent_id: str

    # role 是消息角色。
    role: MessageRole

    # content 是消息正文，大型工具结果后续会改为 artifact 引用。
    content: str

    # sequence 是会话内递增序号，保证 append-only 顺序。
    sequence: int

    # estimated_tokens 是粗略 token 估算，用于上下文预算。
    estimated_tokens: int

    # compacted 表示该消息是否已经被摘要覆盖；即使为 true，原文也不删除。
    compacted: bool = False

    # created_at 是消息创建时间。
    created_at: datetime = field(default_factory=utc_now)
