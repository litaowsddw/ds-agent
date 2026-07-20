"""Workflow executor behaviour tests."""

import asyncio

import pytest

from packages.workflow.executor import WorkflowExecutor


def test_executor_records_budget_rejection_before_llm_call() -> None:
    """A cap failure is visible in the trace and never reaches the LLM callback."""

    calls: list[dict[str, object]] = []

    def llm(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        calls.append(config)
        return {"text": "should not run"}

    definition = {
        "execution_limits": {"max_llm_calls": 0},
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "draft", "type": "llm", "config": {}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "draft"},
            {"source": "draft", "target": "end"},
        ],
    }

    result = WorkflowExecutor(llm_gateway=llm).execute(definition, {"text": "hello"})

    assert result.status == "failed"
    assert calls == []
    assert [node.node_id for node in result.node_runs] == ["start", "draft"]
    assert result.node_runs[-1].status == "failed"
    assert "LLM" in result.node_runs[-1].error_message


def test_executor_runs_parallel_branches_and_joins_their_outputs() -> None:
    """A valid fan-out/fan-in workflow must not lose branch state or crash."""

    def llm(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        return {"text": str(config["label"])}

    definition = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "draft", "type": "llm", "config": {"label": "draft"}},
            {"id": "review", "type": "llm", "config": {"label": "review"}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "draft"},
            {"source": "start", "target": "review"},
            {"source": "draft", "target": "end"},
            {"source": "review", "target": "end"},
        ],
    }

    result = WorkflowExecutor(llm_gateway=llm).execute(definition, {"text": "hello"})

    assert result.status == "succeeded"
    assert {node.node_id for node in result.node_runs} == {"start", "draft", "review", "end"}
    assert result.output_data == {
        "result": {
            "draft": {"text": "draft"},
            "review": {"text": "review"},
        }
    }


@pytest.mark.asyncio
async def test_async_executor_runs_parallel_branches_and_joins_their_outputs() -> None:
    """The production async path has the same fan-out/fan-in guarantee."""

    async def llm(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        return {"text": str(config["label"])}

    definition = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "draft", "type": "llm", "config": {"label": "draft"}},
            {"id": "review", "type": "llm", "config": {"label": "review"}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "draft"},
            {"source": "start", "target": "review"},
            {"source": "draft", "target": "end"},
            {"source": "review", "target": "end"},
        ],
    }

    result = await WorkflowExecutor(llm_gateway=llm).execute_async(
        definition, {"text": "hello"}
    )

    assert result.status == "succeeded"
    assert {node.node_id for node in result.node_runs} == {"start", "draft", "review", "end"}
    assert result.output_data == {
        "result": {
            "draft": {"text": "draft"},
            "review": {"text": "review"},
        }
    }


@pytest.mark.parametrize(
    ("input_data", "expected_node", "unexpected_node"),
    [
        ({"status": "approved"}, "approved", "rejected"),
        ({"status": "pending"}, "rejected", "approved"),
    ],
)
def test_executor_routes_condition_to_exactly_one_named_branch(
    input_data: dict[str, str], expected_node: str, unexpected_node: str
) -> None:
    """A Condition must run one true/false route instead of fanning out to both."""

    def llm(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        return {"text": str(config["label"])}

    definition = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {
                "id": "approved_check",
                "type": "condition",
                "config": {"left": "{{input.status}}", "operator": "equals", "value": "approved"},
            },
            {"id": "approved", "type": "llm", "config": {"label": "approved"}},
            {"id": "rejected", "type": "llm", "config": {"label": "rejected"}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "approved_check"},
            {"source": "approved_check", "target": "approved", "branch": "true"},
            {"source": "approved_check", "target": "rejected", "branch": "false"},
            {"source": "approved", "target": "end"},
            {"source": "rejected", "target": "end"},
        ],
    }

    result = WorkflowExecutor(llm_gateway=llm).execute(definition, input_data)

    assert result.status == "succeeded"
    assert {node.node_id for node in result.node_runs} == {
        "start",
        "approved_check",
        expected_node,
        "end",
    }
    assert unexpected_node not in {node.node_id for node in result.node_runs}
    condition = next(node for node in result.node_runs if node.node_id == "approved_check")
    assert condition.output_data["branch"] == ("true" if expected_node == "approved" else "false")


@pytest.mark.asyncio
async def test_async_executor_supports_exists_condition_against_upstream_output() -> None:
    """Production async execution may test a direct upstream output safely."""

    async def llm(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        return {"text": str(config["label"])}

    definition = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "prepare", "type": "llm", "config": {"label": "available"}},
            {
                "id": "has_result",
                "type": "condition",
                "config": {"left": "{{upstream.prepare.text}}", "operator": "exists"},
            },
            {"id": "continue", "type": "llm", "config": {"label": "continue"}},
            {"id": "fallback", "type": "llm", "config": {"label": "fallback"}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "prepare"},
            {"source": "prepare", "target": "has_result"},
            {"source": "has_result", "target": "continue", "branch": "true"},
            {"source": "has_result", "target": "fallback", "branch": "false"},
            {"source": "continue", "target": "end"},
            {"source": "fallback", "target": "end"},
        ],
    }

    result = await WorkflowExecutor(llm_gateway=llm).execute_async(definition, {})

    assert result.status == "succeeded"
    assert {node.node_id for node in result.node_runs} == {
        "start",
        "prepare",
        "has_result",
        "continue",
        "end",
    }


def test_executor_retries_only_retryable_llm_failures_and_records_attempt_count() -> None:
    calls: list[dict[str, object]] = []

    def llm(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        calls.append(config)
        assert "reliability" not in config
        if len(calls) == 1:
            raise ConnectionError("temporary upstream reset")
        return {"text": "recovered"}

    definition = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {
                "id": "draft",
                "type": "llm",
                "config": {"reliability": {"max_attempts": 3}},
            },
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "draft"},
            {"source": "draft", "target": "end"},
        ],
    }

    result = WorkflowExecutor(llm_gateway=llm).execute(definition, {})

    assert result.status == "succeeded"
    assert len(calls) == 2
    draft_run = next(node for node in result.node_runs if node.node_id == "draft")
    assert draft_run.attempt_count == 2
    assert draft_run.last_error == ""


def test_llm_retry_cannot_bypass_the_run_llm_call_cap() -> None:
    calls = 0

    def llm(_config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        nonlocal calls
        calls += 1
        raise ConnectionError("temporary upstream reset")

    definition = {
        "execution_limits": {"max_llm_calls": 1},
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {
                "id": "draft",
                "type": "llm",
                "config": {"reliability": {"max_attempts": 3}},
            },
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "draft"},
            {"source": "draft", "target": "end"},
        ],
    }

    result = WorkflowExecutor(llm_gateway=llm).execute(definition, {})

    assert result.status == "failed"
    assert calls == 1
    draft_run = next(node for node in result.node_runs if node.node_id == "draft")
    assert draft_run.attempt_count == 1
    assert "LLM" in draft_run.last_error


@pytest.mark.asyncio
async def test_async_executor_retries_retryable_rag_failures() -> None:
    calls = 0

    async def rag(_config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("temporary vector store reset")
        return {"text": "retrieved"}

    definition = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {
                "id": "search",
                "type": "rag",
                "config": {"reliability": {"max_attempts": 2, "timeout_seconds": 3}},
            },
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "search"},
            {"source": "search", "target": "end"},
        ],
    }

    result = await WorkflowExecutor(rag_search=rag).execute_async(definition, {})

    assert result.status == "succeeded"
    assert calls == 2
    search_run = next(node for node in result.node_runs if node.node_id == "search")
    assert search_run.attempt_count == 2


@pytest.mark.asyncio
async def test_async_timeout_stops_waiting_without_automatic_retry() -> None:
    calls = 0

    async def llm(_config: dict[str, object], _node_input: dict[str, object]) -> dict[str, str]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(5)
        return {"text": "too late"}

    definition = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {
                "id": "draft",
                "type": "llm",
                "config": {
                    "reliability": {"max_attempts": 3, "timeout_seconds": 1}
                },
            },
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "draft"},
            {"source": "draft", "target": "end"},
        ],
    }

    result = await WorkflowExecutor(llm_gateway=llm).execute_async(definition, {})

    assert result.status == "failed"
    assert calls == 1
    draft_run = next(node for node in result.node_runs if node.node_id == "draft")
    assert draft_run.attempt_count == 1
    assert draft_run.last_error.startswith("llm 节点等待外部服务超过 1 秒")
    assert "已尝试 1 次，最多允许 3 次" in draft_run.error_message
