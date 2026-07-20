"""Strict parsing tests for per-node reliability policies."""

import pytest

from packages.workflow.reliability import (
    NodeReliabilityPolicy,
    WorkflowReliabilityConfigurationError,
    reliability_policy_for_node,
)


def test_default_llm_policy_keeps_one_attempt_and_async_timeout() -> None:
    policy = reliability_policy_for_node("llm", {})

    assert policy == NodeReliabilityPolicy()
    assert policy.async_timeout_seconds() == 30


@pytest.mark.parametrize(
    "config",
    [
        {"reliability": []},
        {"reliability": {"max_attempts": True}},
        {"reliability": {"max_attempts": 0}},
        {"reliability": {"max_attempts": 4}},
        {"reliability": {"timeout_seconds": "30"}},
        {"reliability": {"timeout_seconds": 0}},
        {"reliability": {"timeout_seconds": 121}},
        {"reliability": {"backoff_ms": 100}},
    ],
)
def test_reliability_policy_rejects_non_strict_shapes(config: dict[str, object]) -> None:
    with pytest.raises(WorkflowReliabilityConfigurationError):
        reliability_policy_for_node("rag", config)


def test_tool_reliability_is_rejected_before_any_automatic_retry() -> None:
    with pytest.raises(WorkflowReliabilityConfigurationError, match="Tool/MCP"):
        reliability_policy_for_node("tool", {"reliability": {"max_attempts": 2}})
