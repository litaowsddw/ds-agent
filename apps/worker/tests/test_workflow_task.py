"""Workflow Celery 任务测试。"""

from apps.worker.app.tasks.workflow import execute_workflow


def test_execute_workflow_task_function() -> None:
    """Celery 任务函数本身应能执行 Workflow DSL。"""

    definition = {
        "version": "1.0",
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "llm", "type": "llm", "config": {"prompt": "hello"}},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "llm"},
            {"source": "llm", "target": "end"},
        ],
    }

    result = execute_workflow.run(definition=definition, input_data={"text": "hello"})

    assert result["status"] == "succeeded"
    assert len(result["node_runs"]) == 3

