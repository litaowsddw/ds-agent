"""身份存储与权限隔离测试。"""

import pytest

from apps.api.app.domain.identity import OrganizationRole
from apps.api.app.services.identity_store import IdentityStore


def test_owner_can_create_team_and_add_member() -> None:
    """组织 owner 应该可以创建群组并添加成员。"""

    # store 是独立内存存储，避免测试之间共享状态。
    store = IdentityStore()

    # owner 是组织创建者。
    owner = store.register_user(
        email="owner@example.com",
        display_name="Owner",
        password="password123",
    )

    # developer 是将被加入组织的开发者。
    developer = store.register_user(
        email="developer@example.com",
        display_name="Developer",
        password="password123",
    )

    organization = store.create_organization(creator_user_id=owner.user_id, name="研发组织")
    team = store.create_team(actor_user_id=owner.user_id, org_id=organization.org_id, name="平台组")

    membership = store.add_member(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        target_user_id=developer.user_id,
        role=OrganizationRole.DEVELOPER,
        team_ids=[team.team_id],
    )

    assert membership.role == OrganizationRole.DEVELOPER
    assert membership.team_ids == [team.team_id]


def test_viewer_cannot_create_team() -> None:
    """viewer 只能读取组织和群组，不能创建群组。"""

    store = IdentityStore()

    owner = store.register_user(
        email="owner2@example.com",
        display_name="Owner",
        password="password123",
    )
    viewer = store.register_user(
        email="viewer@example.com",
        display_name="Viewer",
        password="password123",
    )
    organization = store.create_organization(creator_user_id=owner.user_id, name="只读组织")
    store.add_member(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        target_user_id=viewer.user_id,
        role=OrganizationRole.VIEWER,
    )

    with pytest.raises(PermissionError):
        store.create_team(actor_user_id=viewer.user_id, org_id=organization.org_id, name="非法群组")


def test_user_cannot_read_other_org_teams() -> None:
    """用户不能读取自己未加入组织的群组。"""

    store = IdentityStore()

    alice = store.register_user(
        email="alice@example.com",
        display_name="Alice",
        password="password123",
    )
    bob = store.register_user(
        email="bob@example.com",
        display_name="Bob",
        password="password123",
    )
    alice_org = store.create_organization(creator_user_id=alice.user_id, name="Alice 组织")
    store.create_organization(creator_user_id=bob.user_id, name="Bob 组织")

    with pytest.raises(PermissionError):
        store.list_teams(actor_user_id=bob.user_id, org_id=alice_org.org_id)
