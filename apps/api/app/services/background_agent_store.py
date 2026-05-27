"""后台 Agent 管理服务。

管理 Memory Agent、MCP Health Agent、Workflow Monitor Agent
和 Queue Governor Agent 的配置和状态。
"""

from apps.api.app.domain.background_agent import (
    BackgroundAgentConfig,
    BackgroundAgentStatus,
    BackgroundAgentType,
)
from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission
from apps.api.app.storage.local_state import local_state_store


class BackgroundAgentStore:
    """管理后台 Agent 配置和状态。"""

    def __init__(self, identity: IdentityStore) -> None:
        self.identity = identity
        self.configs_by_id: dict[str, BackgroundAgentConfig] = {}
        self._load_state()

    def register_agent(
        self,
        actor_user_id: str,
        org_id: str,
        agent_type: BackgroundAgentType,
        interval_seconds: int = 300,
    ) -> BackgroundAgentConfig:
        """注册后台 Agent。"""
        self.identity.assert_org_access(actor_user_id, org_id, Permission.AGENT_CREATE)
        existing = self._find_by_type(org_id, agent_type)
        if existing is not None:
            existing.enabled = True
            existing.interval_seconds = interval_seconds
            self._save_state()
            return existing

        config = BackgroundAgentConfig(
            config_id=new_id("bga"),
            org_id=org_id,
            agent_type=agent_type,
            interval_seconds=interval_seconds,
        )
        self.configs_by_id[config.config_id] = config
        self._save_state()
        return config

    def list_agents(self, actor_user_id: str, org_id: str) -> list[BackgroundAgentConfig]:
        """列出组织内后台 Agent。"""
        self.identity.assert_org_access(actor_user_id, org_id, Permission.ORGANIZATION_READ)
        return [c for c in self.configs_by_id.values() if c.org_id == org_id]

    def trigger_run(self, actor_user_id: str, config_id: str) -> BackgroundAgentConfig:
        """手动触发后台 Agent 运行。"""
        config = self._require_config(config_id)
        self.identity.assert_org_access(actor_user_id, config.org_id, Permission.AGENT_CREATE)
        config.status = BackgroundAgentStatus.RUNNING
        config.last_run_at = utc_now()
        # MVP 阶段只更新状态，实际执行由 Celery 任务完成。
        config.status = BackgroundAgentStatus.IDLE
        self._save_state()
        return config

    def disable_agent(self, actor_user_id: str, config_id: str) -> BackgroundAgentConfig:
        """禁用后台 Agent。"""
        config = self._require_config(config_id)
        self.identity.assert_org_access(actor_user_id, config.org_id, Permission.AGENT_CREATE)
        config.enabled = False
        config.status = BackgroundAgentStatus.DISABLED
        self._save_state()
        return config

    def _find_by_type(
        self, org_id: str, agent_type: BackgroundAgentType
    ) -> BackgroundAgentConfig | None:
        for c in self.configs_by_id.values():
            if c.org_id == org_id and c.agent_type == agent_type:
                return c
        return None

    def _require_config(self, config_id: str) -> BackgroundAgentConfig:
        config = self.configs_by_id.get(config_id)
        if config is None:
            raise ValueError("后台 Agent 配置不存在")
        return config

    def _load_state(self) -> None:
        state = local_state_store.load_bucket("background_agents", {})
        if not isinstance(state, dict):
            return
        self.configs_by_id = state.get("configs_by_id", self.configs_by_id)

    def _save_state(self) -> None:
        local_state_store.save_bucket(
            "background_agents",
            {"configs_by_id": self.configs_by_id},
        )


background_agent_store = BackgroundAgentStore(identity=identity_store)
