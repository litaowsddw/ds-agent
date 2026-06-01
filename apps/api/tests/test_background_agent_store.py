"""后台 Agent 管理测试。"""

from apps.api.app.domain.background_agent import BackgroundAgentType
from apps.api.app.services.background_agent_store import (
    BackgroundAgentStore,
)
from apps.api.app.services.identity_store import IdentityStore


def _setup() -> tuple[BackgroundAgentStore, str, str]:
    identity = IdentityStore()
    user = identity.register_user(email="bg@test.com", display_name="BG", password="pass")
    org = identity.create_organization(creator_user_id=user.user_id, name="BG Org")
    store = BackgroundAgentStore(identity=identity)
    return store, user.user_id, org.org_id


def test_register_and_list_background_agents() -> None:
    """注册后应可列出后台 Agent。"""
    store, uid, oid = _setup()

    config = store.register_agent(
        actor_user_id=uid,
        org_id=oid,
        agent_type=BackgroundAgentType.MEMORY,
        interval_seconds=120,
    )
    assert config.config_id.startswith("bga_")
    assert config.agent_type == BackgroundAgentType.MEMORY

    agents = store.list_agents(actor_user_id=uid, org_id=oid)
    assert len(agents) == 1


def test_disable_background_agent() -> None:
    """禁用后台 Agent 应更新状态。"""
    store, uid, oid = _setup()

    config = store.register_agent(
        actor_user_id=uid,
        org_id=oid,
        agent_type=BackgroundAgentType.MCP_HEALTH,
    )
    disabled = store.disable_agent(actor_user_id=uid, config_id=config.config_id)
    assert disabled.enabled is False
    assert disabled.status == "disabled"


def test_duplicate_register_updates_existing() -> None:
    """重复注册同类型后台 Agent 应更新配置。"""
    store, uid, oid = _setup()

    store.register_agent(
        actor_user_id=uid,
        org_id=oid,
        agent_type=BackgroundAgentType.MEMORY,
        interval_seconds=100,
    )
    updated = store.register_agent(
        actor_user_id=uid,
        org_id=oid,
        agent_type=BackgroundAgentType.MEMORY,
        interval_seconds=200,
    )
    assert updated.interval_seconds == 200

    agents = store.list_agents(actor_user_id=uid, org_id=oid)
    assert len(agents) == 1
