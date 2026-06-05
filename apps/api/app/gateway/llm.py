"""LLM Gateway（异步限流版本）。

该模块提供统一的模型调用入口。组织级模型供应商配置通过数据库服务读取，
并以 OpenAI-compatible 协议调用真实供应商。
限流使用 Redis 全局令牌桶。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.gateway.rate_limiter import (
    HybridRateLimiter,
    RateLimitExceeded,
    rate_limiter,
)
from packages.runtime.prompt_compiler import PromptContextCompiler


class LLMProvider(Protocol):
    """LLM Provider 协议。"""

    def generate(self, request: "LLMCallRequest") -> "LLMCallResponse":
        """生成模型响应。"""


@dataclass(slots=True)
class LLMCallRequest:
    """LLM 调用请求。"""
    provider: str
    model: str
    prompt: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    prefix_hash: str = ""


@dataclass(slots=True)
class LLMCallResponse:
    """LLM 调用响应。"""
    text: str
    provider: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMCallLog:
    """LLM 调用日志。"""
    call_id: str
    provider: str
    model: str
    prompt_preview: str
    prefix_hash: str
    status: str
    usage: dict[str, int]
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


class GatewayProviderError(RuntimeError):
    """Provider 调用错误。"""


class OpenAICompatibleProvider:
    """OpenAI-compatible Provider 适配器。"""

    def __init__(self, base_url: str, api_key: str, provider_key: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.provider_key = provider_key
        self.timeout_seconds = timeout_seconds

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        if not self.api_key:
            raise GatewayProviderError("模型供应商未配置 API Key")

        payload = self._build_payload(request)
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        http_request = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
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
            provider=self.provider_key,
            model=request.model,
            usage=usage,
            raw={"id": body.get("id"), "object": body.get("object")},
        )

    def stream_generate(self, request: LLMCallRequest):
        if not self.api_key:
            raise GatewayProviderError("Model provider API key is not configured")

        payload = self._build_payload(request, stream=True)
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        http_request = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        body = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = self._extract_stream_delta(body)
                    if delta:
                        yield delta
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise GatewayProviderError(f"Model provider HTTP {exc.code}: {detail[:300]}") from exc
        except URLError as exc:
            raise GatewayProviderError(f"Model provider network error: {exc.reason}") from exc

    def _build_payload(self, request: LLMCallRequest, stream: bool = False) -> dict[str, Any]:
        payload = {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            **{key: value for key, value in request.parameters.items() if value is not None},
        }
        if stream:
            payload["stream"] = True
        return payload

    def _extract_text(self, body: dict[str, Any]) -> str:
        choices = body.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return str(message.get("content", ""))

    def _extract_stream_delta(self, body: dict[str, Any]) -> str:
        choices = body.get("choices", [])
        if not choices:
            return ""
        delta = choices[0].get("delta", {})
        return str(delta.get("content", "") or "")

    def _extract_usage(self, body: dict[str, Any]) -> dict[str, int]:
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
    """LLM 统一网关（支持异步限流）。"""

    def __init__(
        self,
        providers: dict[str, LLMProvider] | None = None,
        limiter: HybridRateLimiter | None = None,
    ) -> None:
        self.providers = providers or {}
        self.call_logs: list[LLMCallLog] = []
        self.prompt_compiler = PromptContextCompiler()
        self.limiter = limiter or rate_limiter

    async def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        """执行一次 LLM 调用并记录日志（异步版本，支持 Redis 限流）。"""

        provider = self._resolve_provider(request)
        if provider is None:
            error_message = f"未注册 LLM Provider：{request.provider}"
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise GatewayProviderError(error_message)

        try:
            await self._check_rate_limit(request)
            response = provider.generate(request)
        except RateLimitExceeded:
            error_message = "RateLimitExceeded: 限流超限，LLM 调用已被拒绝"
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise
        except Exception as exc:
            error_message = self._normalize_error(exc)
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise GatewayProviderError(error_message) from exc

        self._append_log(
            request=request, status="succeeded", usage=response.usage, error_message=""
        )
        return response

    async def stream_generate(self, request: LLMCallRequest) -> AsyncIterator[str]:
        """Stream an LLM response through the configured provider."""

        provider = self._resolve_provider(request)
        if provider is None:
            error_message = f"Unregistered LLM provider: {request.provider}"
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise GatewayProviderError(error_message)

        try:
            await self._check_rate_limit(request)
            streamer = getattr(provider, "stream_generate", None)
            if streamer is None:
                response = provider.generate(request)
                for index in range(0, len(response.text), 24):
                    yield response.text[index : index + 24]
                usage = response.usage
            else:
                completion_chars = 0
                for chunk in streamer(request):
                    completion_chars += len(chunk)
                    yield chunk
                usage = {
                    "prompt_tokens": 0,
                    "completion_tokens": max(1, completion_chars // 4) if completion_chars else 0,
                }
        except RateLimitExceeded:
            error_message = "RateLimitExceeded: LLM call rejected by rate limiter"
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise
        except Exception as exc:
            error_message = self._normalize_error(exc)
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise GatewayProviderError(error_message) from exc

        self._append_log(request=request, status="succeeded", usage=usage, error_message="")

    async def generate_from_workflow_node(
        self,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> dict[str, Any]:
        """为 Workflow LLM 节点提供调用入口。"""

        provider = str(config.get("provider") or "")
        model = str(config.get("model") or "")
        if not provider or not model:
            raise GatewayProviderError("LLM 节点缺少真实模型供应商或模型配置")
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
        response = await self.generate(request)
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
        """解析内置 Provider（数据库 Provider 在调用时由上层注入）。"""
        return self.providers.get(request.provider)

    def _compile_workflow_prompt(
        self, config: dict[str, Any], node_input: dict[str, Any]
    ) -> dict[str, object]:
        """编译 Workflow LLM 节点 Prompt。"""
        immutable_prefix = {
            "system_prompt": config.get("system_prompt", ""),
            "model": config.get("model", ""),
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

    async def _check_rate_limit(self, request: LLMCallRequest) -> None:
        """检查 LLM 调用限流（异步 Redis 版本）。"""
        scope = str(request.metadata.get("org_id") or request.metadata.get("scope") or "global")
        provider_key = f"llm:provider:{request.provider}"
        model_key = f"llm:model:{request.provider}:{request.model}"
        scope_key = f"llm:scope:{scope}"
        for key in (provider_key, model_key, scope_key):
            await self.limiter.require(key=key, tokens=1)

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

    def _normalize_error(self, exc: Exception) -> str:
        """标准化 Provider 错误。"""
        return f"{exc.__class__.__name__}: {exc}"


# llm_gateway 是 API 进程默认 LLM Gateway。
llm_gateway = LLMGateway()
