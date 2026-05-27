"""Workflow Celery 任务。

MVP 阶段 Worker 任务接收发布版本 DSL 和输入，执行后返回结构化结果。
API 进程中的 RunStore 会记录 Celery task id；生产版本会改为数据库共享运行状态。
"""

from apps.worker.app.celery_app import celery_app
from packages.workflow.executor import WorkflowExecutor


@celery_app.task(name="agentflow.workflow.execute")
def execute_workflow(
    definition: dict[str, object], input_data: dict[str, object]
) -> dict[str, object]:
    """执行 Workflow DSL。"""

    # executor 是纯 Python 执行器，不依赖 API 进程状态。
    executor = WorkflowExecutor()

    # result 是本次执行的结构化结果。
    result = executor.execute(definition=definition, input_data=input_data)

    return {
        "status": result.status,
        "output_data": result.output_data,
        "error_message": result.error_message,
        "node_runs": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "status": node.status,
                "input_data": node.input_data,
                "output_data": node.output_data,
                "error_message": node.error_message,
                "elapsed_ms": node.elapsed_ms,
            }
            for node in result.node_runs
        ],
    }
