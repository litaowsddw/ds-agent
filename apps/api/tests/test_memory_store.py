"""MemoryStore 测试。"""

import pytest

from apps.api.app.domain.identity import OrganizationRole
from apps.api.app.domain.memory import MemoryType
from apps.api.app.services.agent_store import AgentStore
from apps.api.app.services.identity_store import IdentityStore
from apps.api.app.services.memory_store import MemoryStore


def test_memory_can_be_created_and_recalled_by_agent() -> None:
    """有权限用户可以写入并召回 Agent 记忆。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    memory_store = MemoryStore(identity=identity, agents=agent_store)

    owner = identity.register_user("memory-owner@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Memory 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Memory Agent", "")

    memory_store.create_memory(
        actor_user_id=owner.user_id,
        agent_id=agent.agent_id,
        memory_type=MemoryType.PREFERENCE,
        content="用户偏好使用中文回答。",
        summary="用户偏好中文回答。",
    )

    memories = memory_store.recall_memories(
        actor_user_id=owner.user_id,
        agent_id=agent.agent_id,
        query="中文",
    )

    assert memories[0].summary == "用户偏好中文回答。"


def test_viewer_cannot_create_memory() -> None:
    """viewer 不能写入长期记忆。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    memory_store = MemoryStore(identity=identity, agents=agent_store)

    owner = identity.register_user("memory-owner-2@example.com", "Owner", "password123")
    viewer = identity.register_user("memory-viewer@example.com", "Viewer", "password123")
    organization = identity.create_organization(owner.user_id, "Memory Viewer 组织")
    identity.add_member(owner.user_id, organization.org_id, viewer.user_id, OrganizationRole.VIEWER)
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Memory Agent", "")

    with pytest.raises(PermissionError):
        memory_store.create_memory(
            actor_user_id=viewer.user_id,
            agent_id=agent.agent_id,
            memory_type=MemoryType.FACT,
            content="viewer 不应写入",
            summary="viewer 不应写入",
        )
