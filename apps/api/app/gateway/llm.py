"""LLM Gateway。

该模块提供统一的模型调用入口。内置 mock provider 用于本地开发和测试；
组织级模型供应商配置通过 ModelProviderStore 读取，并以 OpenAI-compatible
协议调用真实供应商，例如 OpenAI、DeepSeek、通义千问、智谱、Moonshot 等。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.domain.model_provider import ModelProviderConfig
from apps.api.app.gateway.rate_limiter import LocalTokenBucketRateLimiter, RateLimitExceeded, rate_limiter
from packages.runtime.prompt_compiler import PromptContextCompiler


class LLMProvider(Protocol):
    """LLM Provider 协议。"""

    def generate(self, request: "LLMCallRequest") -> "LLMCallResponse":
        """生成模型响应。"""


@dataclass(slots=True)
class LLMCallRequest:
    """LLM 调用请求。"""

    # provider 是模型供应商名称，例如 mock、openai、deepseek。
    provider: str

    # model 是模型名称。
    model: str

    # prompt 是最终发送给模型的文本。
    prompt: str

    # parameters 是模型参数，例如 temperature、max_tokens。
    parameters: dict[str, Any] = field(default_factory=dict)

    # metadata 保存调用来源、组织、用户等信息，禁止放密钥。
    metadata: dict[str, Any] = field(default_factory=dict)

    # prefix_hash 是 Reasonix 风格稳定前缀 hash，用于观测 prefix-cache 命中。
    prefix_hash: str = ""


@dataclass(slots=True)
class LLMCallResponse:
    """LLM 调用响应。"""

    # text 是模型输出文本。
    text: str

    # provider 是实际响应的供应商。
    provider: str

    # model 是实际响应的模型。
    model: str

    # usage 保存 token 和缓存命中统计。
    usage: dict[str, int] = field(default_factory=dict)

    # raw 保存标准化前的响应摘要，禁止包含密钥。
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMCallLog:
    """LLM 调用日志。"""

    # call_id 是调用日志唯一标识。
    call_id: str

    # provider 是供应商名称。
    provider: str

    # model 是模型名称。
    model: str

    # prompt_preview 是提示词预览，避免日志写入过长内容。
    prompt_preview: str

    # prefix_hash 是稳定前缀 hash。
    prefix_hash: str

    # status 是调用状态，succeeded 或 failed。
    status: str

    # usage 保存 token 和缓存命中统计。
    usage: dict[str, int]

    # error_message 是失败时的标准化错误。
    error_message: str = ""

    # metadata 保存调用来源。
    metadata: dict[str, Any] = field(default_factory=dict)

    # created_at 是调用时间。
    created_at: datetime = field(default_factory=utc_now)


class GatewayProviderError(RuntimeError):
    """Provider 调用错误。"""


class MockLLMProvider:
    """Mock LLM Provider。"""

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        """返回确定性的 mock 模型响应。"""

        prompt_tokens = max(1, len(request.prompt) // 4)
        return LLMCallResponse(
            text=f"[mock-llm] {request.prompt}".strip(),
            provider=request.provider,
            model=request.model,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 8,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": prompt_tokens,
            },
            raw={"mock": True},
        )


class OpenAICompatibleProvider:
    """OpenAI-compatible Provider 适配器。"""

    def __init__(self, config: ModelProviderConfig, timeout_seconds: int = 30) -> None:
        # config 保存组织级供应商配置，包含 base_url、api_key 和可用模型。
        self.config = config

        # timeout_seconds 是 HTTP 请求超时时间。
        self.timeout_seconds = timeout_seconds

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        """通过 /chat/completions 调用 OpenAI-compatible API。"""

        if not self.config.api_key:
            raise GatewayProviderError("模型供应商未配置 API Key")

        payload = {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            **{key: value for key, value in request.parameters.items() if value is not None},
        }
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        http_request = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise GatewayProviderError(f"模型供应商 HTTP {exc.code}: {detail[:300]}") from exc
        except URLError as exc:
            raise GatewayProviderError(f"模型供应商网络错误: {exc.reason}") from exc

        text = self._extract_text(body)
        usage = self._extract_usage(body)
        return LLMCallResponse(
            text=text,
            provider=self.config.provider_key,
            model=request.model,
            usage=usage,
            raw={"id": body.get("id"), "object": body.get("object")},
        )

    def _extract_text(self, body: dict[str, Any]) -> str:
        """从 OpenAI-compatible 响应中提取文本。"""

        choices = body.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return str(message.get("content", ""))

    def _extract_usage(self, body: dict[str, Any]) -> dict[str, int]:
        """从响应中提取 token 使用量。"""

        usage = body.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cache_hit_tokens": int(usage.get("prompt_cache_hit_tokens", 0) or 0),
            "cache_miss_tokens": int(usage.get("prompt_cache_miss_tokens", prompt_tokens) or 0),
        }


class LLMGateway:
    """LLM 统一网关。"""

    def __init__(
        self,
        providers: dict[str, LLMProvider] | None = None,
        limiter: LocalTokenBucketRateLimiter | None = None,
    ) -> None:
        # providers 保存内置 Provider 注册表。
        self.providers = providers or {"mock": MockLLMProvider()}

        # call_logs 保存调用日志，MVP 阶段使用内存存储。
        self.call_logs: list[LLMCallLog] = []

        # prompt_compiler 负责编译 Reasonix 风格三段式 Prompt。
        self.prompt_compiler = PromptContextCompiler()

        # limiter 是 Gateway 调用前的统一限流器。
        self.limiter = limiter or rate_limiter

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        """执行一次 LLM 调用并记录日志。"""

        provider = self._resolve_provider(request)
        if provider is None:
            error_message = f"未注册 LLM Provider：{request.provider}"
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise GatewayProviderError(error_message)

        try:
            self._check_rate_limit(request=request)
            response = provider.generate(request)
        except RateLimitExceeded:
            error_message = "RateLimitExceeded: 限流超限，LLM 调用已被拒绝"
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise
        except Exception as exc:
            error_message = self._normalize_error(exc)
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise GatewayProviderError(error_message) from exc

        self._append_log(request=request, status="succeeded", usage=response.usage, error_message="")
        return response

    def generate_from_workflow_node(
        self,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> dict[str, Any]:
        """为 Workflow LLM 节点提供调用入口。"""

        provider = str(config.get("provider", "mock"))
        model = str(config.get("model", "mock-model"))
        compiled_prompt = self._compile_workflow_prompt(config=config, node_input=node_input)
        prompt = str(compiled_prompt["compiled_prompt"])
        prefix_hash = str(compiled_prompt["prefix_hash"])

        request = LLMCallRequest(
            provider=provider,
            model=model,
            prompt=prompt,
            parameters={
                "temperature": config.get("temperature", 0),
                "max_tokens": config.get("max_tokens"),
            },
            metadata={
                "source": "workflow_node",
                "org_id": config.get("_org_id", ""),
                "actor_user_id": config.get("_actor_user_id", ""),
                "upstream_node_count": len(node_input.get("upstream", {})),
            },
            prefix_hash=prefix_hash,
        )
        response = self.generate(request)
        return {
            "text": response.text,
            "provider": response.provider,
            "model": response.model,
            "usage": response.usage,
            "upstream": node_input.get("upstream", {}),
            "prefix_hash": prefix_hash,
        }

    def list_logs(self) -> list[LLMCallLog]:
        """返回 LLM 调用日志。"""

        return list(self.call_logs)

    def _resolve_provider(self, request: LLMCallRequest) -> LLMProvider | None:
        """解析内置或组织级模型供应商。"""

        static_provider = self.providers.get(request.provider)
        if static_provider is not None:
            return static_provider

        org_id = str(request.metadata.get("org_id", ""))
        actor_user_id = str(request.metadata.get("actor_user_id", ""))
        if not org_id or not actor_user_id:
            return None

        from apps.api.app.services.model_provider_store import model_provider_store

        config = model_provider_store.get_by_key(
            actor_user_id=actor_user_id,
            org_id=org_id,
            provider_key=request.provider,
            raise_if_missing=False,
        )
        if config is None or not config.is_enabled:
            return None
        return OpenAICompatibleProvider(config=config)

    def _compile_workflow_prompt(self, config: dict[str, Any], node_input: dict[str, Any]) -> dict[str, object]:
        """编译 Workflow LLM 节点 Prompt。"""

        immutable_prefix = {
            "system_prompt": config.get("system_prompt", ""),
            "model": config.get("model", "mock-model"),
            "tool_schemas": config.get("tool_schemas", []),
            "output_contract": config.get("output_contract", {}),
        }
        append_only_log = {"upstream": node_input.get("upstream", {})}
        current_turn = {
            "prompt": config.get("prompt", ""),
            "workflow_input": node_input.get("workflow_input", {}),
        }
        return self.prompt_compiler.compile(
            immutable_prefix=immutable_prefix,
            append_only_log=append_only_log,
            current_turn=current_turn,
        )

    def _append_log(
        self,
        request: LLMCallRequest,
        status: str,
        usage: dict[str, int],
        error_message: str,
    ) -> None:
        """追加调用日志。"""

        prompt_preview = request.prompt[:160]
        safe_metadata = {
            key: value
            for key, value in request.metadata.items()
            if key not in {"api_key", "authorization"}
        }
        self.call_logs.append(
            LLMCallLog(
                call_id=new_id("llm"),
                provider=request.provider,
                model=request.model,
                prompt_preview=prompt_preview,
                prefix_hash=request.prefix_hash,
                status=status,
                usage=usage,
                error_message=error_message,
                metadata=safe_metadata,
            )
        )

    def _check_rate_limit(self, request: LLMCallRequest) -> None:
        """检查 LLM 调用限流。"""

        scope = str(request.metadata.get("org_id") or request.metadata.get("scope") or "global")
        provider_key = f"llm:provider:{request.provider}"
        model_key = f"llm:model:{request.provider}:{request.model}"
        scope_key = f"llm:scope:{scope}"
        for key in (provider_key, model_key, scope_key):
            self.limiter.require(key=key, tokens=1)

    def _normalize_error(self, exc: Exception) -> str:
        """标准化 Provider 错误。"""

        return f"{exc.__class__.__name__}: {exc}"


# llm_gateway 是 API 进程默认 LLM Gateway。
llm_gateway = LLMGateway()
