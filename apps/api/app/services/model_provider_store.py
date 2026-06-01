"""模型供应商配置存储服务。"""

from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.domain.model_provider import ModelProviderConfig
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission
from apps.api.app.storage.local_state import local_state_store


class ModelProviderStore:
    """管理组织隔离的模型供应商配置。"""

    def __init__(self, identity: IdentityStore) -> None:
        # identity 用于校验用户是否拥有组织访问权限。
        self.identity = identity

        # providers_by_id 保存所有模型供应商配置。
        self.providers_by_id: dict[str, ModelProviderConfig] = {}
        self._load_state()

    def create_provider(
        self,
        actor_user_id: str,
        org_id: str,
        provider_key: str,
        display_name: str,
        base_url: str,
        api_key: str,
        models: list[str],
        default_model: str,
    ) -> ModelProviderConfig:
        """创建或覆盖同组织下同 key 的模型供应商配置。"""

        self.identity.assert_org_access(actor_user_id, org_id, Permission.ORGANIZATION_READ)
        normalized_key = provider_key.strip().lower()
        if not normalized_key:
            raise ValueError("供应商 key 不能为空")
        normalized_models = [model.strip() for model in models if model.strip()]
        if not normalized_models:
            raise ValueError("至少需要配置一个模型")

        existing = self.get_by_key(actor_user_id, org_id, normalized_key, raise_if_missing=False)
        if existing is not None:
            existing.display_name = display_name.strip() or normalized_key
            existing.base_url = base_url.rstrip("/")
            existing.api_key = api_key
            existing.models = normalized_models
            existing.default_model = default_model.strip() or normalized_models[0]
            existing.is_enabled = True
            existing.updated_at = utc_now()
            self._save_state()
            return existing

        provider = ModelProviderConfig(
            provider_id=new_id("mdl"),
            org_id=org_id,
            provider_key=normalized_key,
            display_name=display_name.strip() or normalized_key,
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            models=normalized_models,
            default_model=default_model.strip() or normalized_models[0],
            created_by=actor_user_id,
        )
        self.providers_by_id[provider.provider_id] = provider
        self._save_state()
        return provider

    def list_providers(self, actor_user_id: str, org_id: str) -> list[ModelProviderConfig]:
        """列出用户可访问组织下的模型供应商配置。"""

        self.identity.assert_org_access(actor_user_id, org_id, Permission.ORGANIZATION_READ)
        providers = [
            provider for provider in self.providers_by_id.values() if provider.org_id == org_id
        ]
        return sorted(providers, key=lambda provider: provider.updated_at, reverse=True)

    def get_by_key(
        self,
        actor_user_id: str,
        org_id: str,
        provider_key: str,
        raise_if_missing: bool = True,
    ) -> ModelProviderConfig | None:
        """按组织和 key 读取供应商配置。"""

        self.identity.assert_org_access(actor_user_id, org_id, Permission.ORGANIZATION_READ)
        normalized_key = provider_key.strip().lower()
        for provider in self.providers_by_id.values():
            if provider.org_id == org_id and provider.provider_key == normalized_key:
                return provider
        if raise_if_missing:
            raise ValueError("模型供应商配置不存在")
        return None

    def _load_state(self) -> None:
        """从本地状态文件恢复模型供应商配置。"""

        state = local_state_store.load_bucket("model_providers", {})
        if not isinstance(state, dict):
            return
        self.providers_by_id = state.get("providers_by_id", self.providers_by_id)

    def _save_state(self) -> None:
        """把模型供应商配置保存到本地状态文件。"""

        local_state_store.save_bucket(
            "model_providers",
            {"providers_by_id": self.providers_by_id},
        )


# model_provider_store 是 MVP 阶段的进程内模型供应商配置存储。
model_provider_store = ModelProviderStore(identity=identity_store)
