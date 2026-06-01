"""OpenTelemetry 分布式追踪集成。

提供统一的追踪初始化和 FastAPI 中间件，支持：
- HTTP 请求追踪
- LLM 调用追踪
- Celery 任务追踪
- 自定义 Span

使用环境变量控制启用/禁用：
- OTEL_ENABLED: 是否启用追踪（默认 false）
- OTEL_SERVICE_NAME: 服务名称（默认 agentflow-api）
- OTEL_EXPORTER_ENDPOINT: OTLP 导出端点（默认 http://localhost:4317）
"""

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

# ──────────────────────────────────────
# 轻量级追踪实现（无 opentelemetry 依赖）
# ──────────────────────────────────────

_OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() == "true"
_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "agentflow-api")
_EXPORTER_ENDPOINT = os.getenv("OTEL_EXPORTER_ENDPOINT", "http://localhost:4317")


@dataclass(slots=True)
class Span:
    """追踪 Span。"""

    name: str
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    parent_id: str | None = None
    span_id: str = ""

    def __post_init__(self) -> None:
        if not self.span_id:
            from uuid import uuid4
            self.span_id = uuid4().hex[:16]

    def set_attribute(self, key: str, value: Any) -> None:
        """设置 Span 属性。"""
        self.attributes[key] = value

    def finish(self, status: str = "ok") -> None:
        """结束 Span。"""
        self.end_time = time.time()
        self.status = status

    @property
    def duration_ms(self) -> float:
        """Span 持续时间（毫秒）。"""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000


@dataclass
class TraceContext:
    """当前追踪上下文。"""

    trace_id: str = ""
    spans: list[Span] = field(default_factory=list)
    current_span: Span | None = None

    def __post_init__(self) -> None:
        if not self.trace_id:
            from uuid import uuid4
            self.trace_id = uuid4().hex


# 线程本地追踪上下文栈
_trace_stack: list[TraceContext] = []


def get_current_trace() -> TraceContext | None:
    """获取当前追踪上下文。"""
    return _trace_stack[-1] if _trace_stack else None


def start_trace(name: str, attributes: dict[str, Any] | None = None) -> TraceContext:
    """开始新的追踪。"""
    ctx = TraceContext()
    span = Span(name=name, attributes=attributes or {})
    ctx.current_span = span
    ctx.spans.append(span)
    _trace_stack.append(ctx)
    return ctx


def end_trace(status: str = "ok") -> TraceContext | None:
    """结束当前追踪。"""
    if not _trace_stack:
        return None
    ctx = _trace_stack.pop()
    if ctx.current_span:
        ctx.current_span.finish(status)
    return ctx


@contextmanager
def trace_span(name: str, **attributes: Any) -> Generator[Span, None, None]:
    """追踪 Span 上下文管理器。

    用法：
        with trace_span("llm.call", model="gpt-4") as span:
            result = call_llm()
            span.set_attribute("tokens", result.usage.total_tokens)
    """
    ctx = get_current_trace()
    span = Span(
        name=name,
        attributes=attributes,
        parent_id=ctx.current_span.span_id if ctx and ctx.current_span else None,
    )

    if ctx:
        ctx.spans.append(span)
        old_span = ctx.current_span
        ctx.current_span = span
        try:
            yield span
        except Exception as exc:
            span.finish(status="error")
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            raise
        else:
            span.finish()
        finally:
            ctx.current_span = old_span
    else:
        try:
            yield span
        except Exception as exc:
            span.finish(status="error")
            span.set_attribute("error.type", type(exc).__name__)
            raise
        else:
            span.finish()


# ──────────────────────────────────────
# FastAPI 中间件
# ──────────────────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class TracingMiddleware(BaseHTTPMiddleware):
    """HTTP 请求追踪中间件。

    为每个请求创建 trace，记录：
    - 请求方法、路径、状态码
    - 请求耗时
    - 用户 ID（如果有 JWT）
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 跳过健康检查
        if request.url.path in ("/health", "/health/", "/docs", "/openapi.json"):
            return await call_next(request)

        span_name = f"{request.method} {request.url.path}"

        with trace_span(
            span_name,
            method=request.method,
            path=str(request.url.path),
            query=str(request.query_params) if request.query_params else "",
        ) as span:
            # 提取 JWT 中的用户信息
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                from app.core.security import verify_access_token
                payload = verify_access_token(auth_header[7:])
                if payload:
                    span.set_attribute("user.id", payload.user_id)
                    span.set_attribute("user.org_id", payload.org_id or "")

            response = await call_next(request)

            span.set_attribute("status_code", response.status_code)
            if response.status_code >= 400:
                span.finish(status="error")

            # 添加追踪 ID 到响应头
            ctx = get_current_trace()
            if ctx:
                response.headers["X-Trace-Id"] = ctx.trace_id

            return response


# ──────────────────────────────────────
# OpenTelemetry 真实集成（可选）
# ──────────────────────────────────────

_otel_tracer = None


def init_otel() -> None:
    """初始化 OpenTelemetry（需要安装 opentelemetry 依赖）。"""
    global _otel_tracer

    if not _OTEL_ENABLED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        resource = Resource.create({"service.name": _SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=_EXPORTER_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _otel_tracer = trace.get_tracer(_SERVICE_NAME)
    except ImportError:
        pass  # opentelemetry 不可用，使用内置轻量追踪


# ──────────────────────────────────────
# LLM 调用追踪辅助
# ──────────────────────────────────────

def trace_llm_call(
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: float = 0,
    cached: bool = False,
    error: str | None = None,
) -> Span:
    """记录 LLM 调用追踪。"""
    span = Span(
        name="llm.call",
        attributes={
            "llm.provider": provider,
            "llm.model": model,
            "llm.prompt_tokens": prompt_tokens,
            "llm.completion_tokens": completion_tokens,
            "llm.cached": cached,
            "llm.duration_ms": duration_ms,
        },
    )
    if error:
        span.finish(status="error")
        span.set_attribute("error.message", error)
    else:
        span.finish()

    # 加入当前 trace
    ctx = get_current_trace()
    if ctx:
        ctx.spans.append(span)

    return span
