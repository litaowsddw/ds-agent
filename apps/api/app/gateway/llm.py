"""LLM Gateway（异步限流版本）。

该模块提供统一的模型调用入口。组织级模型供应商配置通过数据库服务读取，
并以 OpenAI-compatible 协议调用真实供应商。
限流使用 Redis 全局令牌桶。
"""

import json
from collections.abc import Awaitable, Callable
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
from apps.api.app.services.db.metering_db import UsageEventInput
from apps.api.app.services.metering import (
    NormalizedUsage,
    UsageRecorder,
    UsageTerminalOutcome,
    normalize_usage,
    unavailable_usage,
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
    # Chat callers may supply an already assembled OpenAI-compatible message
    # sequence.  ``prompt`` remains required for existing runtime callers and
    # for observability previews, while ``messages`` preserves role boundaries
    # for providers that support native chat payloads.
    messages: list[dict[str, str]] | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    prefix_hash: str = ""


@dataclass(slots=True)
class LLMCallResponse:
    """LLM 调用响应。"""
    text: str
    provider: str
    model: str
    usage: dict[str, object] = field(default_factory=dict)
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
    usage: dict[str, object]
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


class GatewayProviderError(RuntimeError):
    """Provider 调用错误。"""


@dataclass(frozen=True, slots=True)
class LLMStreamChunk:
    """A provider stream item containing text or the final provider usage."""

    text: str = ""
    usage: dict[str, object] | None = None


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
                        yield LLMStreamChunk(text=delta)
                    usage = self._extract_usage(body)
                    if usage:
                        yield LLMStreamChunk(usage=usage)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise GatewayProviderError(f"Model provider HTTP {exc.code}: {detail[:300]}") from exc
        except URLError as exc:
            raise GatewayProviderError(f"Model provider network error: {exc.reason}") from exc

    def _build_payload(self, request: LLMCallRequest, stream: bool = False) -> dict[str, Any]:
        messages = request.messages or [{"role": "user", "content": request.prompt}]
        payload = {
            "model": request.model,
            "messages": messages,
            **{key: value for key, value in request.parameters.items() if value is not None},
        }
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
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

    def _extract_usage(self, body: dict[str, Any]) -> dict[str, object]:
        usage = body.get("usage", {})
        return dict(usage) if isinstance(usage, dict) else {}


class LLMGateway:
    """LLM 统一网关（支持异步限流）。"""

    def __init__(
        self,
        providers: dict[str, LLMProvider] | None = None,
        limiter: HybridRateLimiter | None = None,
        usage_recorder: UsageRecorder | None = None,
    ) -> None:
        self.providers = providers or {}
        self.call_logs: list[LLMCallLog] = []
        self.prompt_compiler = PromptContextCompiler()
        self.limiter = limiter or rate_limiter
        self.usage_recorder = usage_recorder
        # A gateway instance is scoped to one chat request when it is used by
        # the chat route. Keep only provider-reported facts, never a derived
        # count from prompt text.
        self.last_normalized_usage: NormalizedUsage | None = None
        self.last_raw_usage: dict[str, object] = {}

    async def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        """执行一次 LLM 调用并记录日志（异步版本，支持 Redis 限流）。"""

        usage_context = await self._record_started(request)
        provider = self._resolve_provider(request)
        if provider is None:
            error_message = f"未注册 LLM Provider：{request.provider}"
            await self._record_terminal(
                usage_context, dispatch_status="failed", error_category="provider_not_found"
            )
            self._append_log(
                request=request,
                status="failed",
                usage={},
                error_message=error_message,
                call_id=usage_context.gateway_call_id,
            )
            raise GatewayProviderError(error_message)

        try:
            await self._check_rate_limit(request)
            response = provider.generate(request)
        except RateLimitExceeded:
            error_message = "RateLimitExceeded: 限流超限，LLM 调用已被拒绝"
            await self._record_terminal(
                usage_context, dispatch_status="rate_limited", error_category="rate_limit"
            )
            self._append_log(
                request=request,
                status="failed",
                usage={},
                error_message=error_message,
                call_id=usage_context.gateway_call_id,
            )
            raise
        except Exception as exc:
            error_message = self._normalize_error(exc)
            await self._record_terminal(
                usage_context,
                dispatch_status="failed",
                error_category=exc.__class__.__name__,
            )
            self._append_log(
                request=request,
                status="failed",
                usage={},
                error_message=error_message,
                call_id=usage_context.gateway_call_id,
            )
            raise GatewayProviderError(error_message) from exc

        await self._record_terminal(
            usage_context, dispatch_status="succeeded", raw_usage=response.usage
        )
        self.last_raw_usage = dict(response.usage)
        self.last_normalized_usage = normalize_usage(response.usage)
        self._append_log(
            request=request,
            status="succeeded",
            usage=response.usage,
            error_message="",
            call_id=usage_context.gateway_call_id,
        )
        return response

    async def stream_generate(self, request: LLMCallRequest) -> AsyncIterator[str]:
        """Stream an LLM response through the configured provider."""

        self.last_raw_usage = {}
        self.last_normalized_usage = None
        usage_context = await self._record_started(request)
        terminal_recorded = False

        async def record_terminal_once(
            *,
            dispatch_status: str,
            raw_usage: dict[str, object] | None = None,
            error_category: str | None = None,
        ) -> None:
            nonlocal terminal_recorded
            if terminal_recorded:
                return
            terminal_recorded = True
            await self._record_terminal(
                usage_context,
                dispatch_status=dispatch_status,
                raw_usage=raw_usage,
                error_category=error_category,
            )

        provider = self._resolve_provider(request)
        if provider is None:
            error_message = f"Unregistered LLM provider: {request.provider}"
            await record_terminal_once(
                dispatch_status="failed", error_category="provider_not_found"
            )
            self._append_log(
                request=request,
                status="failed",
                usage={},
                error_message=error_message,
                call_id=usage_context.gateway_call_id,
            )
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
                final_usage: dict[str, object] | None = None
                for chunk in streamer(request):
                    if isinstance(chunk, LLMStreamChunk):
                        if chunk.usage is not None:
                            final_usage = chunk.usage
                        if chunk.text:
                            yield chunk.text
                    else:
                        yield str(chunk)
                usage = final_usage or {}
        except RateLimitExceeded:
            error_message = "RateLimitExceeded: LLM call rejected by rate limiter"
            await record_terminal_once(
                dispatch_status="rate_limited", error_category="rate_limit"
            )
            self._append_log(
                request=request,
                status="failed",
                usage={},
                error_message=error_message,
                call_id=usage_context.gateway_call_id,
            )
            raise
        except Exception as exc:
            error_message = self._normalize_error(exc)
            await record_terminal_once(
                dispatch_status="failed", error_category=exc.__class__.__name__
            )
            self._append_log(
                request=request,
                status="failed",
                usage={},
                error_message=error_message,
                call_id=usage_context.gateway_call_id,
            )
            raise GatewayProviderError(error_message) from exc

        else:
            self.last_raw_usage = dict(usage)
            self.last_normalized_usage = normalize_usage(usage) if usage else None
            await record_terminal_once(dispatch_status="succeeded", raw_usage=usage)
            self._append_log(
                request=request,
                status="succeeded",
                usage=usage,
                error_message="",
                call_id=usage_context.gateway_call_id,
            )
        finally:
            if not terminal_recorded:
                await record_terminal_once(
                    dispatch_status="cancelled", error_category="cancelled"
                )
                self._append_log(
                    request=request,
                    status="cancelled",
                    usage={},
                    error_message="stream cancelled before provider completion",
                    call_id=usage_context.gateway_call_id,
                )

    async def generate_from_workflow_node(
        self,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> dict[str, Any]:
        """为 Workflow LLM 节点提供调用入口。"""

        request, compiled = self.build_workflow_request(config, node_input)
        response = await self.generate(request)
        return {
            "text": response.text,
            "provider": response.provider,
            "model": response.model,
            "usage": response.usage,
            "upstream": node_input.get("upstream", {}),
            "prefix_hash": str(compiled["prefix_hash"]),
        }

    def build_workflow_request(
        self, config: dict[str, Any], node_input: dict[str, Any]
    ) -> tuple[LLMCallRequest, dict[str, object]]:
        """Build the shared LLM request for Workflow nodes."""

        provider = str(config.get("provider") or "")
        model = str(config.get("model") or "")
        if not provider or not model:
            raise GatewayProviderError("LLM 节点缺少真实模型供应商或模型配置")
        compiled = self._compile_workflow_prompt(config=config, node_input=node_input)

        request = LLMCallRequest(
            provider=provider,
            model=model,
            prompt=str(compiled["compiled_prompt"]),
            parameters={
                "temperature": config.get("temperature", 0),
                "max_tokens": config.get("max_tokens"),
            },
            metadata={
                "source": "workflow_node",
                "org_id": config.get("_org_id", ""),
                "actor_user_id": config.get("_actor_user_id", ""),
                "agent_id": config.get("_agent_id", ""),
                "workflow_id": config.get("_workflow_id", ""),
                "workflow_version_id": config.get("_workflow_version_id", ""),
                "workflow_run_id": config.get("_workflow_run_id", ""),
                "workflow_node_id": config.get("_workflow_node_id", ""),
                "api_name": "chat.completions",
                "upstream_node_count": len(node_input.get("upstream", {})),
            },
            prefix_hash=str(compiled["prefix_hash"]),
        )
        return request, compiled

    async def stream_generate_from_workflow_node(
        self,
        config: dict[str, Any],
        node_input: dict[str, Any],
        on_text: Callable[[str], Awaitable[None]],
    ) -> dict[str, Any]:
        """Stream Workflow LLM text to a callback and return the node output."""

        request, compiled = self.build_workflow_request(config, node_input)
        parts: list[str] = []
        stream = self.stream_generate(request)
        try:
            async for text in stream:
                parts.append(text)
                await on_text(text)
        finally:
            await stream.aclose()
        return {
            "text": "".join(parts),
            "provider": request.provider,
            "model": request.model,
            "usage": dict(self.last_raw_usage),
            "upstream": node_input.get("upstream", {}),
            "prefix_hash": str(compiled["prefix_hash"]),
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
        usage: dict[str, object],
        error_message: str,
        call_id: str | None = None,
    ) -> None:
        """追加调用日志。"""
        safe_metadata = {
            key: value
            for key, value in request.metadata.items()
            if key not in {"api_key", "authorization"}
        }
        self.call_logs.append(
            LLMCallLog(
                call_id=call_id or new_id("llm"),
                provider=request.provider,
                model=request.model,
                prompt_preview="",
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

    async def _record_started(self, request: LLMCallRequest) -> UsageEventInput:
        """Create a safe attempt context without prompt text or request secrets."""

        metadata = request.metadata
        context = UsageEventInput(
            gateway_call_id=new_id("llm"),
            org_id=str(metadata.get("org_id") or ""),
            source=str(metadata.get("source") or "gateway"),
            api_name=str(metadata.get("api_name") or "llm.generate"),
            provider_key=request.provider,
            model=request.model,
            dispatch_status="started",
            usage_status="unavailable",
            actor_user_id=_optional_metadata_value(metadata, "actor_user_id"),
            agent_id=_optional_metadata_value(metadata, "agent_id"),
            session_id=_optional_metadata_value(metadata, "session_id"),
            workflow_id=_optional_metadata_value(metadata, "workflow_id"),
            workflow_version_id=_optional_metadata_value(metadata, "workflow_version_id"),
            workflow_run_id=_optional_metadata_value(metadata, "workflow_run_id"),
            workflow_node_id=_optional_metadata_value(metadata, "workflow_node_id"),
            dispatched_at=utc_now(),
            prefix_cache_status=("eligible" if request.prefix_hash else "not_applicable"),
        )
        if self.usage_recorder is not None:
            await self.usage_recorder.record_started(context)
        return context

    async def _record_terminal(
        self,
        context: UsageEventInput,
        *,
        dispatch_status: str,
        raw_usage: dict[str, object] | None = None,
        error_category: str | None = None,
    ) -> None:
        if self.usage_recorder is None:
            return
        usage = normalize_usage(raw_usage) if raw_usage else unavailable_usage()
        await self.usage_recorder.record_terminal(
            context.gateway_call_id,
            UsageTerminalOutcome(
                dispatch_status=dispatch_status,
                usage=usage,
                completed_at=utc_now(),
                error_category=error_category,
            ),
        )


def _optional_metadata_value(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return str(value) if value not in (None, "") else None


# llm_gateway 是 API 进程默认 LLM Gateway。
llm_gateway = LLMGateway()
