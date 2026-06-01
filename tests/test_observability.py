"""可观测性模块单元测试 — 追踪、指标、日志。"""

import json
import pytest

# 通过 sys.path 确保可以找到 app 包
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app.core.telemetry import (
    Span,
    TraceContext,
    start_trace,
    end_trace,
    trace_span,
    get_current_trace,
    trace_llm_call,
)
from app.core.metrics import (
    MetricsRegistry,
    Counter,
    Histogram,
    Gauge,
)
from app.core.logging import (
    JSONFormatter,
    ConsoleFormatter,
    set_request_context,
    clear_request_context,
    request_id_var,
    user_id_var,
)


# ──────────────────────────────────────
# 追踪测试
# ──────────────────────────────────────


class TestTracing:
    """分布式追踪测试套件。"""

    def test_span_creation(self) -> None:
        """Span 创建和属性设置。"""
        span = Span(name="test.span")
        assert span.name == "test.span"
        assert span.status == "ok"
        assert span.span_id != ""

        span.set_attribute("key", "value")
        assert span.attributes["key"] == "value"

    def test_span_finish(self) -> None:
        """Span 结束和耗时计算。"""
        span = Span(name="test.finish")
        span.finish()
        assert span.end_time > 0
        assert span.duration_ms >= 0

    def test_span_error_status(self) -> None:
        """Span 错误状态。"""
        span = Span(name="test.error")
        span.finish(status="error")
        assert span.status == "error"

    def test_trace_span_context_manager(self) -> None:
        """trace_span 上下文管理器正常工作。"""
        with trace_span("test.operation", key="value") as span:
            assert span.name == "test.operation"
            assert span.attributes["key"] == "value"
            span.set_attribute("extra", "data")

        assert span.end_time > 0
        assert span.status == "ok"

    def test_trace_span_error_handling(self) -> None:
        """trace_span 异常处理。"""
        try:
            with trace_span("test.error_op") as span:
                raise ValueError("test error")
        except ValueError:
            pass

        assert span.status == "error"
        assert span.attributes.get("error.type") == "ValueError"

    def test_start_and_end_trace(self) -> None:
        """完整追踪生命周期。"""
        ctx = start_trace("test.trace")
        assert ctx is not None
        assert ctx.trace_id != ""
        assert ctx.current_span is not None

        result = end_trace()
        assert result is not None
        assert result.current_span.end_time > 0

    def test_trace_llm_call(self) -> None:
        """LLM 调用追踪记录。"""
        span = trace_llm_call(
            provider="openai",
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            duration_ms=1200,
            cached=False,
        )
        assert span.name == "llm.call"
        assert span.attributes["llm.provider"] == "openai"
        assert span.attributes["llm.model"] == "gpt-4"
        assert span.attributes["llm.prompt_tokens"] == 100
        assert span.status == "ok"

    def test_trace_llm_call_error(self) -> None:
        """LLM 调用错误追踪。"""
        span = trace_llm_call(
            provider="openai",
            model="gpt-4",
            error="Rate limit exceeded",
        )
        assert span.status == "error"
        assert span.attributes["error.message"] == "Rate limit exceeded"


# ──────────────────────────────────────
# 指标测试
# ──────────────────────────────────────


class TestMetrics:
    """Prometheus 指标测试套件。"""

    def test_counter(self) -> None:
        """计数器正常工作。"""
        counter = Counter(name="test_counter")
        assert counter.value == 0.0
        counter.inc()
        assert counter.value == 1.0
        counter.inc(5)
        assert counter.value == 6.0

    def test_histogram(self) -> None:
        """直方图正常工作。"""
        hist = Histogram(name="test_histogram")
        hist.observe(0.5)
        hist.observe(1.0)
        hist.observe(2.5)
        assert hist.count_value == 3
        assert hist.sum_value == 4.0

    def test_gauge(self) -> None:
        """仪表盘正常工作。"""
        gauge = Gauge(name="test_gauge")
        assert gauge.value == 0.0
        gauge.set(10)
        assert gauge.value == 10.0
        gauge.inc(5)
        assert gauge.value == 15.0
        gauge.dec(3)
        assert gauge.value == 12.0

    def test_metrics_registry(self) -> None:
        """指标注册表正常工作。"""
        registry = MetricsRegistry()
        counter = registry.counter("test_reg_counter", "帮助文本")
        counter.inc(3)

        hist = registry.histogram("test_reg_histogram")
        hist.observe(1.0)

        gauge = registry.gauge("test_reg_gauge")
        gauge.set(42)

        # Prometheus 格式输出
        output = registry.collect_prometheus()
        assert "test_reg_counter" in output
        assert "test_reg_histogram" in output
        assert "test_reg_gauge" in output
        assert "3.0" in output
        assert "42.0" in output

    def test_record_llm_call(self) -> None:
        """LLM 调用指标记录。"""
        from app.core import metrics as m
        # 记录一次 LLM 调用
        m.record_llm_call(provider="openai", model="gpt-4", prompt_tokens=100, completion_tokens=50)
        # 验证计数器增加（只检查 > 0，因为其他测试可能也增加了）
        assert m.llm_calls_total.value > 0

    def test_record_cache_access(self) -> None:
        """缓存访问指标记录。"""
        from app.core import metrics as m
        old_hits = m.cache_hits.value
        old_misses = m.cache_misses.value
        m.record_cache_access(hit=True)
        assert m.cache_hits.value > old_hits
        m.record_cache_access(hit=False)
        assert m.cache_misses.value > old_misses


# ──────────────────────────────────────
# 日志测试
# ──────────────────────────────────────


class TestLogging:
    """结构化日志测试套件。"""

    def test_json_formatter(self) -> None:
        """JSON 格式化器输出有效 JSON。"""
        import logging
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert data["logger"] == "test.logger"

    def test_json_formatter_with_context(self) -> None:
        """JSON 格式化器注入请求上下文。"""
        import logging
        set_request_context(request_id="req_123", user_id="usr_456")
        try:
            formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
            record = logging.LogRecord(
                name="test.context",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="With context",
                args=(),
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["request_id"] == "req_123"
            assert data["user_id"] == "usr_456"
        finally:
            clear_request_context()

    def test_console_formatter(self) -> None:
        """Console 格式化器正常工作。"""
        import logging
        formatter = ConsoleFormatter(datefmt="%H:%M:%S")
        record = logging.LogRecord(
            name="test.console",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "WARNING" in output
        assert "Warning message" in output

    def test_clear_request_context(self) -> None:
        """清除请求上下文。"""
        set_request_context(request_id="req_clear", user_id="usr_clear")
        assert request_id_var.get() == "req_clear"
        clear_request_context()
        assert request_id_var.get() == ""
        assert user_id_var.get() == ""
