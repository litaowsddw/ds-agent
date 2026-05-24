"""Workflow Run 存储与执行协调服务。

MVP 阶段使用内存存储。这里负责创建运行记录、执行发布版本、保存节点日志。
异步执行由 Celery 任务入口复用同一个执行器逻辑。
"""

from typing import Any

from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.domain.workflow_run import NodeRun, NodeRunStatus, RunStatus, WorkflowRun
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission
from apps.api.app.services.workflow_store import WorkflowStore, workflow_store
from packages.workflow.executor import WorkflowExecutor, WorkflowExecutionResult


class WorkflowRunStore:
    """管理 Workflow Run 和 Node Run。"""

    def __init__(self, identity: IdentityStore, workflows: WorkflowStore) -> None:
        # identity 用于运行查询和创建权限校验。
        self.identity = identity

        # workflows 用于读取发布版本和工作流元信息。
        self.workflows = workflows

        # runs_by_id 保存 Workflow Run。
        self.runs_by_id: dict[str, WorkflowRun] = {}

        # node_runs_by_run_id 保存每次运行的节点日志。
        self.node_runs_by_run_id: dict[str, list[NodeRun]] = {}

        # executor 是纯 Python 工作流执行器。
        self.executor = WorkflowExecutor()

    def create_run(
        self,
        actor_user_id: str,
        version_id: str,
        input_data: dict[str, Any],
        execute_immediately: bool = True,
    ) -> WorkflowRun:
        """创建 Workflow Run。"""

        version = self.workflows.get_version(actor_user_id=actor_user_id, version_id=version_id)
        workflow = self.workflows.get_workflow(
            actor_user_id=actor_user_id,
            workflow_id=version.workflow_id,
        )
        self.identity.assert_org_access(actor_user_id, version.org_id, Permission.WORKFLOW_CREATE)

        run = WorkflowRun(
            run_id=new_id("run"),
            org_id=version.org_id,
            workflow_id=version.workflow_id,
            version_id=version.version_id,
            agent_id=workflow.agent_id,
            input_data=input_data,
            created_by=actor_user_id,
        )
        self.runs_by_id[run.run_id] = run
        self.node_runs_by_run_id[run.run_id] = []

        if execute_immediately:
            self.execute_run(actor_user_id=actor_user_id, run_id=run.run_id)

        return run

    def execute_run(self, actor_user_id: str, run_id: str) -> WorkflowRun:
        """同步执行 Workflow Run。"""

        run = self.get_run(actor_user_id=actor_user_id, run_id=run_id)
        version = self.workflows.get_version(actor_user_id=actor_user_id, version_id=run.version_id)

        run.status = RunStatus.RUNNING
        run.updated_at = utc_now()

        result = self.executor.execute(definition=version.definition, input_data=run.input_data)
        self._apply_execution_result(run=run, result=result)
        return run

    def attach_celery_task(self, actor_user_id: str, run_id: str, celery_task_id: str) -> WorkflowRun:
        """把 Celery task id 记录到 Workflow Run。"""

        run = self.get_run(actor_user_id=actor_user_id, run_id=run_id)
        run.celery_task_id = celery_task_id
        run.updated_at = utc_now()
        return run

    def get_run(self, actor_user_id: str, run_id: str) -> WorkflowRun:
        """读取 Workflow Run。"""

        run = self.runs_by_id.get(run_id)
        if run is None:
            raise ValueError("Workflow Run 不存在")

        self.identity.assert_org_access(actor_user_id, run.org_id, Permission.ORGANIZATION_READ)
        return run

    def list_node_runs(self, actor_user_id: str, run_id: str) -> list[NodeRun]:
        """列出 Workflow Run 的节点日志。"""

        run = self.get_run(actor_user_id=actor_user_id, run_id=run_id)
        return list(self.node_runs_by_run_id[run.run_id])

    def _apply_execution_result(self, run: WorkflowRun, result: WorkflowExecutionResult) -> None:
        """把执行器结果写入运行记录。"""

        run.status = RunStatus(result.status)
        run.output_data = result.output_data
        run.error_message = result.error_message
        run.updated_at = utc_now()

        node_runs: list[NodeRun] = []
        for index, executed_node in enumerate(result.node_runs, start=1):
            node_runs.append(
                NodeRun(
                    node_run_id=new_id("ndr"),
                    run_id=run.run_id,
                    node_id=executed_node.node_id,
                    node_type=executed_node.node_type,
                    status=NodeRunStatus(executed_node.status),
                    input_data=executed_node.input_data,
                    output_data=executed_node.output_data,
                    error_message=executed_node.error_message,
                    elapsed_ms=executed_node.elapsed_ms,
                    sequence=index,
                )
            )
        self.node_runs_by_run_id[run.run_id] = node_runs


# workflow_run_store 是 MVP 阶段的进程内运行存储。
workflow_run_store = WorkflowRunStore(identity=identity_store, workflows=workflow_store)

