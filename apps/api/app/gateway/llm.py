"""LLM Gateway。

该模块提供 OpenAI-compatible Provider 的最小抽象，并为 Workflow LLM 节点提供
统一调用入口。当前默认使用 Mock Provider，后续接入真实 HTTP Provider、限流、
缓存和密钥管理时不需要改 WorkflowExecutor。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from apps.api.app.domain.identity import new_id, utc_now


class LLMProvider(Protocol):
    """LLM Provider 协议。"""

    def generate(self, request: "LLMCallRequest") -> "LLMCallResponse":
        """生成模型响应。"""


@dataclass(slots=True)
class LLMCallRequest:
    """LLM 调用请求。"""

    # provider 是模型供应商名称，例如 openai、deepseek、mock。
    provider: str

    # model 是模型名称。
    model: str

    # prompt 是最终发送给模型的文本。
    prompt: str

    # parameters 是模型参数，例如 temperature、max_tokens。
    parameters: dict[str, Any] = field(default_factory=dict)

    # metadata 保存调用来源，不能放密钥。
    metadata: dict[str, Any] = field(default_factory=dict)


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
    """Mock LLM Provider。

    该 Provider 不访问网络，用于本地开发、单元测试和无密钥环境。
    """

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        """返回确定性的 mock 模型响应。"""

        # prompt_tokens 是粗略 prompt token 估算，用于后续成本统计接口稳定。
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
    """OpenAI-compatible Provider 适配器骨架。

    当前不直接发起网络请求，只负责形成稳定接口。模块接入密钥管理和 HTTP Client 后，
    这里会向 `/chat/completions` 或兼容端点发送请求。
    """

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        """生成模型响应。"""

        raise GatewayProviderError("OpenAI-compatible Provider 尚未配置 HTTP Client 和密钥")


class LLMGateway:
    """LLM 统一网关。"""

    def __init__(self, providers: dict[str, LLMProvider] | None = None) -> None:
        # providers 保存 Provider 注册表，key 是 provider 名称。
        self.providers = providers or {"mock": MockLLMProvider()}

        # call_logs 保存调用日志，MVP 阶段使用内存存储。
        self.call_logs: list[LLMCallLog] = []

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        """执行一次 LLM 调用并记录日志。"""

        provider = self.providers.get(request.provider)
        if provider is None:
            error_message = f"未注册 LLM Provider：{request.provider}"
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise GatewayProviderError(error_message)

        try:
            response = provider.generate(request)
        except Exception as exc:
            error_message = self._normalize_error(exc)
            self._append_log(request=request, status="failed", usage={}, error_message=error_message)
            raise GatewayProviderError(error_message) from exc

        self._append_log(
            request=request,
            status="succeeded",
            usage=response.usage,
            error_message="",
        )
        return response

    def generate_from_workflow_node(
        self,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> dict[str, Any]:
        """为 Workflow LLM 节点提供调用入口。"""

        # provider 是节点配置中的供应商，默认 mock。
        provider = str(config.get("provider", "mock"))

        # model 是节点配置中的模型，默认 mock-model。
        model = str(config.get("model", "mock-model"))

        # prompt 是节点配置中的提示词。后续 Prompt Compiler 会在这里接入。
        prompt = str(config.get("prompt", ""))

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
                "upstream_node_count": len(node_input.get("upstream", {})),
            },
        )
        response = self.generate(request)
        return {
            "text": response.text,
            "provider": response.provider,
            "model": response.model,
            "usage": response.usage,
            "upstream": node_input.get("upstream", {}),
        }

    def list_logs(self) -> list[LLMCallLog]:
        """返回 LLM 调用日志。"""

        return list(self.call_logs)

    def _append_log(
        self,
        request: LLMCallRequest,
        status: str,
        usage: dict[str, int],
        error_message: str,
    ) -> None:
        """追加调用日志。"""

        # prompt_preview 截断到 160 字符，避免日志过大。
        prompt_preview = request.prompt[:160]

        self.call_logs.append(
            LLMCallLog(
                call_id=new_id("llm"),
                provider=request.provider,
                model=request.model,
                prompt_preview=prompt_preview,
                status=status,
                usage=usage,
                error_message=error_message,
                metadata=request.metadata,
            )
        )

    def _normalize_error(self, exc: Exception) -> str:
        """标准化 Provider 错误。"""

        return f"{exc.__class__.__name__}: {exc}"


# llm_gateway 是 API 进程默认 LLM Gateway。
llm_gateway = LLMGateway()

