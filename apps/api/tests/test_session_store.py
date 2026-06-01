"""SessionStore 测试。"""

import pytest

from apps.api.app.domain.session import MessageRole, SessionQueueMode
from apps.api.app.services.agent_store import AgentStore
from apps.api.app.services.identity_store import IdentityStore
from apps.api.app.services.session_store import SessionStore


def test_session_messages_are_append_only() -> None:
    """Session 消息应该按追加顺序保存。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    session_store = SessionStore(agents=agent_store)

    owner = identity.register_user("session-owner@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Session 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Session Agent", "")
    session = session_store.create_session(owner.user_id, agent.agent_id, SessionQueueMode.QUEUE)

    first_message = session_store.append_message(
        actor_user_id=owner.user_id,
        session_id=session.session_id,
        role=MessageRole.USER,
        content="第一条消息",
    )
    second_message = session_store.append_message(
        actor_user_id=owner.user_id,
        session_id=session.session_id,
        role=MessageRole.ASSISTANT,
        content="第二条消息",
    )

    messages = session_store.list_messages(owner.user_id, session.session_id)

    assert [message.sequence for message in messages] == [1, 2]
    assert first_message.sequence < second_message.sequence


def test_cross_org_user_cannot_read_session() -> None:
    """其他组织用户不能读取 Session。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    session_store = SessionStore(agents=agent_store)

    alice = identity.register_user("session-alice@example.com", "Alice", "password123")
    bob = identity.register_user("session-bob@example.com", "Bob", "password123")
    organization = identity.create_organization(alice.user_id, "Alice Session 组织")
    identity.create_organization(bob.user_id, "Bob Session 组织")
    agent = agent_store.create_agent(alice.user_id, organization.org_id, "Alice Agent", "")
    session = session_store.create_session(alice.user_id, agent.agent_id)

    with pytest.raises(PermissionError):
        session_store.get_session(actor_user_id=bob.user_id, session_id=session.session_id)


def test_compact_session_marks_messages_compacted() -> None:
    """压缩 Session 应写入摘要并标记历史消息。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    session_store = SessionStore(agents=agent_store)

    owner = identity.register_user("session-compact@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Compact 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Compact Agent", "")
    session = session_store.create_session(owner.user_id, agent.agent_id)
    session_store.append_message(
        owner.user_id, session.session_id, MessageRole.USER, "需要压缩的历史"
    )

    compacted_session = session_store.compact_session(
        actor_user_id=owner.user_id,
        session_id=session.session_id,
        summary="用户讨论了上下文压缩。",
    )
    messages = session_store.list_messages(owner.user_id, session.session_id)

    assert compacted_session.compact_summary == "用户讨论了上下文压缩。"
    assert messages[0].compacted is True
