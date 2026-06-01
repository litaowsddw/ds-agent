"""Agent 与 Workspace 服务测试。"""

import pytest

from apps.api.app.domain.agent import WorkspaceFileKind
from apps.api.app.domain.identity import OrganizationRole
from apps.api.app.services.agent_store import AgentStore
from apps.api.app.services.identity_store import IdentityStore


def test_developer_can_create_agent() -> None:
    """developer 应该可以在所属组织内创建 Agent。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)

    owner = identity.register_user("owner-agent@example.com", "Owner", "password123")
    developer = identity.register_user("developer-agent@example.com", "Developer", "password123")
    organization = identity.create_organization(owner.user_id, "Agent 组织")
    identity.add_member(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        target_user_id=developer.user_id,
        role=OrganizationRole.DEVELOPER,
    )

    agent = agent_store.create_agent(
        actor_user_id=developer.user_id,
        org_id=organization.org_id,
        name="Runtime Agent",
        description="负责运行时能力验证",
    )

    workspace = agent_store.get_workspace(actor_user_id=developer.user_id, agent_id=agent.agent_id)

    assert agent.org_id == organization.org_id
    assert WorkspaceFileKind.AGENTS in workspace.files


def test_viewer_cannot_create_agent() -> None:
    """viewer 不能创建 Agent。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)

    owner = identity.register_user("owner-viewer-agent@example.com", "Owner", "password123")
    viewer = identity.register_user("viewer-agent@example.com", "Viewer", "password123")
    organization = identity.create_organization(owner.user_id, "Viewer 组织")
    identity.add_member(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        target_user_id=viewer.user_id,
        role=OrganizationRole.VIEWER,
    )

    with pytest.raises(PermissionError):
        agent_store.create_agent(
            actor_user_id=viewer.user_id,
            org_id=organization.org_id,
            name="非法 Agent",
            description="viewer 不应拥有创建权限",
        )


def test_workspace_file_can_be_updated_by_developer() -> None:
    """developer 可以更新自己组织内 Agent 的 Workspace 文件。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)

    owner = identity.register_user("owner-workspace@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Workspace 组织")
    agent = agent_store.create_agent(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        name="Workspace Agent",
        description="用于测试 Workspace 更新",
    )

    updated_workspace = agent_store.update_workspace_file(
        actor_user_id=owner.user_id,
        agent_id=agent.agent_id,
        file_kind=WorkspaceFileKind.AGENTS,
        content="# AGENTS\n\n新的 Agent 定义。\n",
    )

    assert updated_workspace.files[WorkspaceFileKind.AGENTS].startswith("# AGENTS")
    assert "新的 Agent 定义" in updated_workspace.files[WorkspaceFileKind.AGENTS]
