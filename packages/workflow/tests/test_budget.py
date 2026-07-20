"""Workflow execution-limit unit tests."""

import pytest

from packages.workflow.budget import (
    WorkflowBudgetConfigurationError,
    WorkflowBudgetExceeded,
    WorkflowBudgetGuard,
    WorkflowExecutionLimits,
    execution_limits_from_definition,
)
from packages.workflow.dsl import WorkflowDefinition, WorkflowEdge, WorkflowNode
from packages.workflow.validator import WorkflowValidator


def test_execution_limits_are_opt_in_and_strictly_parsed() -> None:
    assert execution_limits_from_definition({}) == WorkflowExecutionLimits()
    assert execution_limits_from_definition(
        {"execution_limits": {"max_steps": 7, "max_llm_calls": 0}}
    ) == WorkflowExecutionLimits(max_steps=7, max_llm_calls=0)


@pytest.mark.parametrize(
    "definition",
    [
        {"execution_limits": []},
        {"execution_limits": {"max_steps": True}},
        {"execution_limits": {"max_steps": 0}},
        {"execution_limits": {"max_llm_calls": -1}},
        {"execution_limits": {"max_steps": 501}},
        {"execution_limits": {"max_total_tokens": 1000}},
    ],
)
def test_execution_limits_reject_unsafe_or_unimplemented_policy(definition: dict[str, object]) -> None:
    with pytest.raises(WorkflowBudgetConfigurationError):
        execution_limits_from_definition(definition)


def test_guard_blocks_before_exceeding_step_limit_without_consuming_more_budget() -> None:
    guard = WorkflowBudgetGuard(WorkflowExecutionLimits(max_steps=2))

    guard.before_node("start")
    guard.before_node("end")
    with pytest.raises(WorkflowBudgetExceeded) as error:
        guard.before_node("tool")

    assert error.value.limit_name == "max_steps"
    assert error.value.limit == 2
    assert error.value.used == 2
    assert guard.executed_steps == 2


def test_guard_blocks_second_llm_before_external_call_and_allows_non_llm_nodes() -> None:
    guard = WorkflowBudgetGuard(WorkflowExecutionLimits(max_llm_calls=1))

    guard.before_node("start")
    guard.before_node("llm")
    guard.before_node("tool")
    with pytest.raises(WorkflowBudgetExceeded) as error:
        guard.before_node("llm")

    assert error.value.limit_name == "max_llm_calls"
    assert error.value.used == 1
    assert guard.executed_steps == 3
    assert guard.executed_llm_calls == 1


def test_validator_rejects_unimplemented_token_or_cost_cap_before_publish() -> None:
    """Do not silently publish a cap that the runtime cannot truthfully enforce."""

    result = WorkflowValidator().validate(
        WorkflowDefinition(
            version="1.0",
            nodes=[
                WorkflowNode(node_id="start", node_type="start"),
                WorkflowNode(node_id="end", node_type="end"),
            ],
            edges=[WorkflowEdge(source="start", target="end")],
            execution_limits={"max_total_tokens": 1000},
        )
    )

    assert result["valid"] is False
    assert any("max_total_tokens" in str(error) for error in result["errors"])
