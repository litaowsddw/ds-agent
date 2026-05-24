"""Agent Session 与消息存储。

MVP 阶段使用内存存储。这里的关键不是存储介质，而是确定 Session 隔离、append-only
消息顺序和 queue / collect 模式的业务语义。
"""

from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.domain.session import (
    AgentSession,
    MessageRole,
    SessionMessage,
    SessionQueueMode,
    SessionStatus,
)
from apps.api.app.services.agent_store import AgentStore, agent_store


class SessionStore:
    """管理 Agent Session 和 append-only 消息。"""

    def __init__(self, agents: AgentStore) -> None:
        # agents 是 Agent 存储，用于复用 Agent 读取权限和组织隔离。
        self.agents = agents

        # sessions_by_id 保存会话实体，key 是 session_id。
        self.sessions_by_id: dict[str, AgentSession] = {}

        # messages_by_session_id 保存每个会话的消息列表，消息只追加不重排。
        self.messages_by_session_id: dict[str, list[SessionMessage]] = {}

    def create_session(
        self,
        actor_user_id: str,
        agent_id: str,
        queue_mode: SessionQueueMode = SessionQueueMode.QUEUE,
    ) -> AgentSession:
        """创建 Agent Session。"""

        agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)

        session = AgentSession(
            session_id=new_id("ses"),
            org_id=agent.org_id,
            agent_id=agent.agent_id,
            user_id=actor_user_id,
            queue_mode=queue_mode,
        )
        self.sessions_by_id[session.session_id] = session
        self.messages_by_session_id[session.session_id] = []
        return session

    def append_message(
        self,
        actor_user_id: str,
        session_id: str,
        role: MessageRole,
        content: str,
    ) -> SessionMessage:
        """向会话追加一条消息。"""

        session = self.get_session(actor_user_id=actor_user_id, session_id=session_id)

        if session.status == SessionStatus.CLOSED:
            raise ValueError("会话已关闭")

        # messages 是当前会话已有消息列表，只允许 append，不允许插入或重排。
        messages = self.messages_by_session_id[session.session_id]

        # sequence 是新消息序号，从 1 开始递增。
        sequence = len(messages) + 1

        message = SessionMessage(
            message_id=new_id("msg"),
            session_id=session.session_id,
            org_id=session.org_id,
            agent_id=session.agent_id,
            role=role,
            content=content,
            sequence=sequence,
            estimated_tokens=self._estimate_tokens(content),
        )
        messages.append(message)
        session.updated_at = utc_now()
        return message

    def list_messages(self, actor_user_id: str, session_id: str) -> list[SessionMessage]:
        """按 append-only 顺序列出会话消息。"""

        session = self.get_session(actor_user_id=actor_user_id, session_id=session_id)
        return list(self.messages_by_session_id[session.session_id])

    def get_session(self, actor_user_id: str, session_id: str) -> AgentSession:
        """读取会话，并校验操作者有权读取对应 Agent。"""

        session = self.sessions_by_id.get(session_id)
        if session is None:
            raise ValueError("会话不存在")

        self.agents.get_agent(actor_user_id=actor_user_id, agent_id=session.agent_id)
        return session

    def set_running(self, actor_user_id: str, session_id: str) -> AgentSession:
        """把会话标记为运行中。"""

        session = self.get_session(actor_user_id=actor_user_id, session_id=session_id)
        session.status = SessionStatus.RUNNING
        session.updated_at = utc_now()
        return session

    def set_idle(self, actor_user_id: str, session_id: str) -> AgentSession:
        """把会话标记为空闲。"""

        session = self.get_session(actor_user_id=actor_user_id, session_id=session_id)
        session.status = SessionStatus.IDLE
        session.updated_at = utc_now()
        return session

    def compact_session(self, actor_user_id: str, session_id: str, summary: str) -> AgentSession:
        """写入会话压缩摘要，并标记旧消息已被摘要覆盖。"""

        session = self.get_session(actor_user_id=actor_user_id, session_id=session_id)
        session.compact_summary = summary
        session.updated_at = utc_now()

        for message in self.messages_by_session_id[session.session_id]:
            message.compacted = True

        return session

    def _estimate_tokens(self, content: str) -> int:
        """粗略估算 token 数。"""

        # 中文和英文混合场景下，MVP 采用字符数 / 4 的粗略估计，至少为 1。
        return max(1, len(content) // 4)


# session_store 是 MVP 阶段的进程内 Session 存储。
session_store = SessionStore(agents=agent_store)

