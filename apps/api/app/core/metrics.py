"""Prometheus 指标收集。

提供内置的轻量级指标收集器，同时支持 Prometheus 客户端。
指标分类：
- LLM 调用：计数、耗时、Token 使用
- 缓存：命中率、未命中
- 限流：被拒请求
- API：请求计数、响应时间
- Agent：执行计数、成功率
"""

import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────
# 轻量级指标收集器（无 prometheus_client 依赖）
# ──────────────────────────────────────

@dataclass
class Counter:
    """计数器。"""

    name: str
    help_text: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    _value: float = 0.0

    def inc(self, amount: float = 1.0) -> None:
        """增加计数。"""
        self._value += amount

    @property
    def value(self) -> float:
        return self._value


@dataclass
class Histogram:
    """直方图（简化版，记录总和和计数）。"""

    name: str
    help_text: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    _sum: float = 0.0
    _count: int = 0
    _buckets: dict[str, int] = field(default_factory=lambda: {
        "0.01": 0, "0.05": 0, "0.1": 0, "0.5": 0,
        "1.0": 0, "2.0": 0, "5.0": 0, "10.0": 0, "+Inf": 0,
    })

    def observe(self, value: float) -> None:
        """记录一个观测值。"""
        self._sum += value
        self._count += 1
        for bucket in self._buckets:
            if value <= float(bucket):
                self._buckets[bucket] += 1

    @property
    def sum_value(self) -> float:
        return self._sum

    @property
    def count_value(self) -> int:
        return self._count


@dataclass
class Gauge:
    """仪表盘。"""

    name: str
    help_text: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    _value: float = 0.0

    def set(self, value: float) -> None:
        """设置值。"""
        self._value = value

    def inc(self, amount: float = 1.0) -> None:
        """增加值。"""
        self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        """减少值。"""
        self._value -= amount

    @property
    def value(self) -> float:
        return self._value


class MetricsRegistry:
    """指标注册表。"""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}
        self._gauges: dict[str, Gauge] = {}

    def counter(self, name: str, help_text: str = "") -> Counter:
        """获取或创建计数器。"""
        if name not in self._counters:
            self._counters[name] = Counter(name=name, help_text=help_text)
        return self._counters[name]

    def histogram(self, name: str, help_text: str = "") -> Histogram:
        """获取或创建直方图。"""
        if name not in self._histograms:
            self._histograms[name] = Histogram(name=name, help_text=help_text)
        return self._histograms[name]

    def gauge(self, name: str, help_text: str = "") -> Gauge:
        """获取或创建仪表盘。"""
        if name not in self._gauges:
            self._gauges[name] = Gauge(name=name, help_text=help_text)
        return self._gauges[name]

    def collect_prometheus(self) -> str:
        """输出 Prometheus 文本格式。"""
        lines = []

        for name, counter in sorted(self._counters.items()):
            if counter.help_text:
                lines.append(f"# HELP {name} {counter.help_text}")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {counter.value}")

        for name, histogram in sorted(self._histograms.items()):
            if histogram.help_text:
                lines.append(f"# HELP {name} {histogram.help_text}")
            lines.append(f"# TYPE {name} histogram")
            for bucket, count in sorted(histogram._buckets.items(), key=lambda x: float(x[0].replace("+Inf", "inf"))):
                lines.append(f'{name}_bucket{{le="{bucket}"}} {count}')
            lines.append(f"{name}_count {histogram.count_value}")
            lines.append(f"{name}_sum {histogram.sum_value}")

        for name, gauge in sorted(self._gauges.items()):
            if gauge.help_text:
                lines.append(f"# HELP {name} {gauge.help_text}")
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {gauge.value}")

        return "\n".join(lines) + "\n"


# 全局指标注册表
metrics = MetricsRegistry()

# ──────────────────────────────────────
# 预定义指标
# ──────────────────────────────────────

# LLM 调用指标
llm_calls_total = metrics.counter("agentflow_llm_calls_total", "LLM 调用总数")
llm_calls_duration = metrics.histogram("agentflow_llm_call_duration_seconds", "LLM 调用耗时（秒）")
llm_tokens_prompt = metrics.counter("agentflow_llm_prompt_tokens_total", "LLM 输入 Token 总数")
llm_tokens_completion = metrics.counter("agentflow_llm_completion_tokens_total", "LLM 输出 Token 总数")
llm_calls_cached = metrics.counter("agentflow_llm_calls_cached_total", "LLM 缓存命中数")
llm_calls_errors = metrics.counter("agentflow_llm_calls_errors_total", "LLM 调用错误数")

# 缓存指标
cache_hits = metrics.counter("agentflow_cache_hits_total", "缓存命中数")
cache_misses = metrics.counter("agentflow_cache_misses_total", "缓存未命中数")

# 限流指标
rate_limit_rejected = metrics.counter("agentflow_rate_limit_rejected_total", "限流拒绝请求数")

# API 请求指标
api_requests_total = metrics.counter("agentflow_api_requests_total", "API 请求总数")
api_request_duration = metrics.histogram("agentflow_api_request_duration_seconds", "API 请求耗时（秒）")

# Agent 执行指标
agent_executions_total = metrics.counter("agentflow_agent_executions_total", "Agent 执行总数")
agent_executions_success = metrics.counter("agentflow_agent_executions_success_total", "Agent 执行成功数")
agent_executions_failed = metrics.counter("agentflow_agent_executions_failed_total", "Agent 执行失败数")

# Evolver 指标
evolver_cycles_total = metrics.counter("agentflow_evolver_cycles_total", "Evolver 进化周期总数")
evolver_skills_created = metrics.counter("agentflow_evolver_skills_created_total", "Evolver 创建 Skill 数")
evolver_skills_updated = metrics.counter("agentflow_evolver_skills_updated_total", "Evolver 更新 Skill 数")

# 当前活跃数
active_sessions = metrics.gauge("agentflow_active_sessions", "当前活跃会话数")
active_agents = metrics.gauge("agentflow_active_agents", "当前活跃 Agent 数")


# ──────────────────────────────────────
# 便捷函数
# ──────────────────────────────────────

def record_llm_call(
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_seconds: float = 0,
    cached: bool = False,
    error: bool = False,
) -> None:
    """记录 LLM 调用指标。"""
    llm_calls_total.inc()
    llm_calls_duration.observe(duration_seconds)
    llm_tokens_prompt.inc(prompt_tokens)
    llm_tokens_completion.inc(completion_tokens)

    if cached:
        llm_calls_cached.inc()
    if error:
        llm_calls_errors.inc()


def record_cache_access(hit: bool) -> None:
    """记录缓存访问。"""
    if hit:
        cache_hits.inc()
    else:
        cache_misses.inc()


def record_rate_limit() -> None:
    """记录限流事件。"""
    rate_limit_rejected.inc()


def record_api_request(method: str, path: str, status_code: int, duration: float) -> None:
    """记录 API 请求指标。"""
    api_requests_total.inc()
    api_request_duration.observe(duration)


# ──────────────────────────────────────
# Prometheus 客户端集成（可选）
# ──────────────────────────────────────

_PROM_ENABLED = os.getenv("PROM_ENABLED", "false").lower() == "true"
_prom_registry = None


def init_prometheus() -> None:
    """初始化 Prometheus 客户端（需要安装 prometheus_client）。"""
    global _prom_registry

    if not _PROM_ENABLED:
        return

    try:
        from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge, generate_latest

        _prom_registry = CollectorRegistry()

        # 注册标准指标
        prom_llm_calls = Counter(
            "agentflow_llm_calls_total",
            "LLM 调用总数",
            ["provider", "model"],
            registry=_prom_registry,
        )
        prom_llm_duration = Histogram(
            "agentflow_llm_call_duration_seconds",
            "LLM 调用耗时",
            ["provider", "model"],
            registry=_prom_registry,
        )
    except ImportError:
        pass  # prometheus_client 不可用，使用内置收集器


def get_prometheus_metrics() -> str:
    """获取 Prometheus 格式的指标输出。"""
    if _prom_registry is not None:
        try:
            from prometheus_client import generate_latest
            return generate_latest(_prom_registry).decode("utf-8")
        except ImportError:
            pass

    # 降级到内置收集器
    return metrics.collect_prometheus()
