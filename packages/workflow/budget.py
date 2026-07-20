"""Deterministic, pre-execution workflow run limits.

Workflow authors may opt into ``execution_limits`` on the immutable workflow
definition::

    {"execution_limits": {"max_steps": 20, "max_llm_calls": 3}}

These are operational safety limits, not billing limits.  They are enforced
*before* a node or an LLM provider is invoked, so they do not depend on prompt
token estimates or a provider price table.  Provider-reported usage remains
the sole source of truth for metering after an allowed call completes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_LIMIT_KEYS = frozenset({"max_steps", "max_llm_calls"})
_MAX_STEPS_HARD_LIMIT = 500
_MAX_LLM_CALLS_HARD_LIMIT = 100


class WorkflowBudgetConfigurationError(ValueError):
    """The published workflow contains an unsafe or unsupported run limit."""


class WorkflowBudgetExceeded(RuntimeError):
    """A deterministic run limit prevented the next node from executing."""

    def __init__(self, *, limit_name: str, limit: int, used: int) -> None:
        self.limit_name = limit_name
        self.limit = limit
        self.used = used
        label = "节点执行数" if limit_name == "max_steps" else "LLM 调用次数"
        super().__init__(
            f"Workflow 运行预算已耗尽：{label}上限为 {limit}，"
            f"当前已执行 {used} 次；后续节点未执行。"
        )


@dataclass(frozen=True, slots=True)
class WorkflowExecutionLimits:
    """Optional deterministic caps stored with one workflow version."""

    max_steps: int | None = None
    max_llm_calls: int | None = None

    @property
    def enabled(self) -> bool:
        return self.max_steps is not None or self.max_llm_calls is not None


class WorkflowBudgetGuard:
    """Mutable per-run counter used by the executor before each node executes."""

    def __init__(self, limits: WorkflowExecutionLimits) -> None:
        self.limits = limits
        self.executed_steps = 0
        self.executed_llm_calls = 0

    def before_node(self, node_type: str) -> None:
        """Reserve budget for the next node without starting its side effect.

        A rejected node does not consume a budget unit.  This makes failures
        explainable in the persisted node trace and ensures that a limit of
        zero LLM calls can safely run non-LLM nodes.
        """

        if (
            self.limits.max_steps is not None
            and self.executed_steps >= self.limits.max_steps
        ):
            raise WorkflowBudgetExceeded(
                limit_name="max_steps",
                limit=self.limits.max_steps,
                used=self.executed_steps,
            )
        if (
            node_type == "llm"
            and self.limits.max_llm_calls is not None
            and self.executed_llm_calls >= self.limits.max_llm_calls
        ):
            raise WorkflowBudgetExceeded(
                limit_name="max_llm_calls",
                limit=self.limits.max_llm_calls,
                used=self.executed_llm_calls,
            )
        self.executed_steps += 1
        if node_type == "llm":
            self.executed_llm_calls += 1


def execution_limits_from_definition(
    definition: Mapping[str, Any],
) -> WorkflowExecutionLimits:
    """Parse the versioned workflow execution policy with strict types.

    ``bool`` deliberately is not an integer limit.  Unknown policy keys are
    rejected instead of silently downgrading a user's safety expectation.
    Token/cost caps are intentionally absent: without a provider preflight
    reservation protocol and a price contract they could only be estimates,
    which must never be presented or enforced as billing facts.
    """

    raw = definition.get("execution_limits")
    if raw is None:
        return WorkflowExecutionLimits()
    if not isinstance(raw, Mapping):
        raise WorkflowBudgetConfigurationError("execution_limits 必须是对象")

    unknown = sorted(str(key) for key in raw.keys() if key not in _LIMIT_KEYS)
    if unknown:
        raise WorkflowBudgetConfigurationError(
            f"execution_limits 包含不支持的字段：{', '.join(unknown)}"
        )

    return WorkflowExecutionLimits(
        max_steps=_read_limit(
            raw,
            "max_steps",
            hard_max=_MAX_STEPS_HARD_LIMIT,
            allow_zero=False,
        ),
        max_llm_calls=_read_limit(
            raw,
            "max_llm_calls",
            hard_max=_MAX_LLM_CALLS_HARD_LIMIT,
            allow_zero=True,
        ),
    )


def _read_limit(
    raw: Mapping[str, Any],
    name: str,
    *,
    hard_max: int,
    allow_zero: bool,
) -> int | None:
    value = raw.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkflowBudgetConfigurationError(f"execution_limits.{name} 必须是整数")
    minimum = 0 if allow_zero else 1
    if value < minimum or value > hard_max:
        raise WorkflowBudgetConfigurationError(
            f"execution_limits.{name} 必须在 {minimum} 到 {hard_max} 之间"
        )
    return value
