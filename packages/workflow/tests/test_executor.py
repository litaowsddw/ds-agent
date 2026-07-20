"""Workflow executor behaviour tests."""

import pytest

from packages.workflow.executor import WorkflowExecutor


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
