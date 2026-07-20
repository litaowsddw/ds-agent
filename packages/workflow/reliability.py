"""Bounded, side-effect-aware reliability policies for workflow nodes.

The policy deliberately belongs to an individual node configuration, rather
than a process-wide retry middleware.  This makes it versioned with the
workflow definition and prevents an author from silently applying retries to
an MCP action that might create, send, or delete something remotely.

Only LLM and RAG nodes are eligible today.  A Tool/MCP node must be retried by
an explicit future idempotency protocol, not by this generic executor layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_POLICY_KEY = "reliability"
_ALLOWED_POLICY_KEYS = frozenset({"max_attempts", "timeout_seconds"})
_RETRYABLE_NODE_TYPES = frozenset({"llm", "rag"})

# Keep retries and the request lifetime bounded even when an author writes a
# definition directly instead of using the UI.
MAX_ATTEMPTS_HARD_LIMIT = 3
MAX_TIMEOUT_SECONDS_HARD_LIMIT = 120
DEFAULT_ASYNC_TIMEOUT_SECONDS = 30


class WorkflowReliabilityConfigurationError(ValueError):
    """A workflow version declares an unsupported node reliability policy."""


class WorkflowNodeTimeout(TimeoutError):
    """The async executor stopped waiting for an external node response."""


class WorkflowSyncTimeoutUnsupported(RuntimeError):
    """The synchronous test-only executor cannot safely enforce wall time."""


@dataclass(frozen=True, slots=True)
class NodeReliabilityPolicy:
    """A strict, bounded policy stored in one node's ``config.reliability``."""

    max_attempts: int = 1
    # ``None`` means no author-selected timeout.  Production ``execute_async``
    # still applies ``DEFAULT_ASYNC_TIMEOUT_SECONDS`` to all LLM/RAG callbacks.
    timeout_seconds: int | None = None

    @property
    def is_configured(self) -> bool:
        return self.max_attempts != 1 or self.timeout_seconds is not None

    def async_timeout_seconds(self) -> int:
        """Return a finite timeout for the production async execution path."""

        return self.timeout_seconds or DEFAULT_ASYNC_TIMEOUT_SECONDS


def reliability_policy_for_node(
    node_type: str,
    config: Mapping[str, Any],
) -> NodeReliabilityPolicy:
    """Parse a node policy with no type coercion or unknown fields.

    Keeping the shape small is intentional: retry delay/backoff, predicates,
    and arbitrary exception rules all require a durable operational contract
    before they can be safely exposed to workflow authors.
    """

    raw = config.get(_POLICY_KEY)
    if raw is None:
        return NodeReliabilityPolicy()
    if node_type not in _RETRYABLE_NODE_TYPES:
        raise WorkflowReliabilityConfigurationError(
            f"{node_type} 节点不支持 reliability；Tool/MCP 节点不会自动重试"
        )
    if not isinstance(raw, Mapping):
        raise WorkflowReliabilityConfigurationError("reliability 必须是对象")

    unknown = sorted(str(key) for key in raw.keys() if key not in _ALLOWED_POLICY_KEYS)
    if unknown:
        raise WorkflowReliabilityConfigurationError(
            f"reliability 包含不支持的字段：{', '.join(unknown)}"
        )

    return NodeReliabilityPolicy(
        max_attempts=_read_positive_int(
            raw,
            "max_attempts",
            default=1,
            hard_max=MAX_ATTEMPTS_HARD_LIMIT,
        ),
        timeout_seconds=_read_optional_positive_int(
            raw,
            "timeout_seconds",
            hard_max=MAX_TIMEOUT_SECONDS_HARD_LIMIT,
        ),
    )


def strip_reliability_policy(config: Mapping[str, Any]) -> dict[str, Any]:
    """Keep executor-only policy data out of provider/RAG callback payloads."""

    return {key: value for key, value in config.items() if key != _POLICY_KEY}


def is_retryable_node_error(exc: Exception) -> bool:
    """Return whether an error is safe to retry for side-effect-free nodes.

    Timeouts intentionally return ``False``.  Even LLM retries after a client
    timeout can duplicate a still-running provider request and its token cost.
    Configuration and validation errors are also never retried.
    """

    if isinstance(exc, WorkflowNodeTimeout | TimeoutError):
        return False
    return isinstance(exc, ConnectionError | OSError)


def _read_positive_int(
    raw: Mapping[str, Any],
    name: str,
    *,
    default: int,
    hard_max: int,
) -> int:
    value = raw.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkflowReliabilityConfigurationError(f"reliability.{name} 必须是整数")
    if value < 1 or value > hard_max:
        raise WorkflowReliabilityConfigurationError(
            f"reliability.{name} 必须在 1 到 {hard_max} 之间"
        )
    return value


def _read_optional_positive_int(
    raw: Mapping[str, Any],
    name: str,
    *,
    hard_max: int,
) -> int | None:
    value = raw.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkflowReliabilityConfigurationError(f"reliability.{name} 必须是整数")
    if value < 1 or value > hard_max:
        raise WorkflowReliabilityConfigurationError(
            f"reliability.{name} 必须在 1 到 {hard_max} 之间"
        )
    return value
