"""Workflow 领域模型。"""

from dataclasses import dataclass, field
from datetime import datetime

from apps.api.app.domain.identity import utc_now


@dataclass(slots=True)
class Workflow:
    """工作流元信息。"""

    # workflow_id 是工作流唯一标识。
    workflow_id: str

    # org_id 是工作流所属组织。
    org_id: str

    # agent_id 是工作流绑定的 Agent。
    agent_id: str

    # name 是工作流名称。
    name: str

    # description 是工作流说明。
    description: str

    # draft_definition 保存当前草稿 DSL。
    draft_definition: dict[str, object]

    # published_version_id 保存当前发布版本 ID。
    published_version_id: str | None = None

    # created_by 是创建者用户 ID。
    created_by: str = ""

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)

    # updated_at 是更新时间。
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class WorkflowVersion:
    """工作流发布版本。"""

    # version_id 是版本唯一标识。
    version_id: str

    # workflow_id 是所属工作流。
    workflow_id: str

    # org_id 是所属组织。
    org_id: str

    # version_number 是递增版本号。
    version_number: int

    # definition 是发布时冻结的 DSL。
    definition: dict[str, object]

    # created_by 是发布者用户 ID。
    created_by: str

    # created_at 是发布时间。
    created_at: datetime = field(default_factory=utc_now)
