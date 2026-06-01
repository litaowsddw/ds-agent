"""Agent 与 Workspace 领域模型。

Agent 是工作流、Skill、MCP、Memory 和后台服务的运行主体。模块 3 的目标是
让每个 Agent 都明确绑定组织、可选群组和独立 Workspace。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from apps.api.app.domain.identity import utc_now


class WorkspaceFileKind(StrEnum):
    """Agent Workspace 文件类型。"""

    AGENTS = "AGENTS.md"
    SOUL = "SOUL.md"
    TOOLS = "TOOLS.md"
    MEMORY = "MEMORY.md"


@dataclass(slots=True)
class Agent:
    """Agent 实体。"""

    # agent_id 是 Agent 唯一标识，后续 Workflow Run 和 Session 都会引用它。
    agent_id: str

    # org_id 是 Agent 所属组织，是最重要的租户隔离字段。
    org_id: str

    # team_id 是 Agent 可选所属群组，空值表示组织级 Agent。
    team_id: str | None

    # name 是 Agent 展示名称。
    name: str

    # description 是 Agent 用途说明。
    description: str

    # created_by 是创建 Agent 的用户 ID。
    created_by: str

    # created_at 是 Agent 创建时间。
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class AgentWorkspace:
    """Agent Workspace 聚合。

    Workspace 保存 Agent 运行时需要的提示词文件。MVP 阶段存储在内存，
    后续会迁移到数据库和对象存储。
    """

    # workspace_id 是 Workspace 唯一标识。
    workspace_id: str

    # org_id 是 Workspace 所属组织。
    org_id: str

    # agent_id 是 Workspace 所属 Agent。
    agent_id: str

    # files 保存 Workspace 文件内容，key 是 WorkspaceFileKind。
    files: dict[WorkspaceFileKind, str]

    # updated_by 是最后更新 Workspace 的用户 ID。
    updated_by: str

    # updated_at 是最后更新时间。
    updated_at: datetime = field(default_factory=utc_now)
