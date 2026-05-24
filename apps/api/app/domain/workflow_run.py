"""Workflow 运行领域模型。

WorkflowRun 表示一次已发布工作流版本的执行实例；NodeRun 表示一次节点执行记录。
它们是后续运行详情、失败重试、成本统计和可观测性的基础。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from apps.api.app.domain.identity import utc_now


class RunStatus(StrEnum):
    """Workflow Run 状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    TIMEOUT = "timeout"


class NodeRunStatus(StrEnum):
    """Node Run 状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class WorkflowRun:
    """工作流运行实例。"""

    # run_id 是运行实例唯一标识。
    run_id: str

    # org_id 是运行实例所属组织。
    org_id: str

    # workflow_id 是运行的工作流 ID。
    workflow_id: str

    # version_id 是运行的发布版本 ID。
    version_id: str

    # agent_id 是运行绑定的 Agent ID。
    agent_id: str

    # input_data 是本次运行输入。
    input_data: dict[str, Any]

    # status 是运行状态机当前状态。
    status: RunStatus = RunStatus.PENDING

    # output_data 是运行成功后的输出。
    output_data: dict[str, Any] = field(default_factory=dict)

    # error_message 是运行失败时的错误摘要。
    error_message: str = ""

    # celery_task_id 是异步任务 ID，便于后续查询 Worker 侧状态。
    celery_task_id: str | None = None

    # created_by 是发起运行的用户 ID。
    created_by: str = ""

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)

    # updated_at 是最后更新时间。
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class NodeRun:
    """工作流节点运行记录。"""

    # node_run_id 是节点运行记录唯一标识。
    node_run_id: str

    # run_id 是所属 Workflow Run。
    run_id: str

    # node_id 是工作流节点 ID。
    node_id: str

    # node_type 是工作流节点类型。
    node_type: str

    # status 是节点运行状态。
    status: NodeRunStatus

    # input_data 是节点输入。
    input_data: dict[str, Any]

    # output_data 是节点输出。
    output_data: dict[str, Any] = field(default_factory=dict)

    # error_message 是节点失败时的错误摘要。
    error_message: str = ""

    # elapsed_ms 是节点耗时毫秒。
    elapsed_ms: int = 0

    # sequence 是节点执行顺序。
    sequence: int = 0

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)

