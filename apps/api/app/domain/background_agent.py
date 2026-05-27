"""后台 Agent 领域模型。

后台 Agent 负责自动化维护任务，例如记忆压缩、MCP 健康检查、
工作流监控和队列治理。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from apps.api.app.domain.identity import utc_now


class BackgroundAgentType(StrEnum):
    """后台 Agent 类型。"""

    MEMORY = "memory"
    MCP_HEALTH = "mcp_health"
    WORKFLOW_MONITOR = "workflow_monitor"
    QUEUE_GOVERNOR = "queue_governor"


class BackgroundAgentStatus(StrEnum):
    """后台 Agent 运行状态。"""

    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass(slots=True)
class BackgroundAgentConfig:
    """后台 Agent 配置。"""

    # config_id 是配置唯一标识。
    config_id: str

    # org_id 是后台 Agent 所属组织。
    org_id: str

    # agent_type 是后台 Agent 类型。
    agent_type: BackgroundAgentType

    # enabled 表示是否启用。
    enabled: bool = True

    # interval_seconds 是执行间隔秒数。
    interval_seconds: int = 300

    # status 是当前运行状态。
    status: BackgroundAgentStatus = BackgroundAgentStatus.IDLE

    # last_run_at 是上次运行时间。
    last_run_at: datetime | None = None

    # last_error 是上次运行错误。
    last_error: str = ""

    # created_at 是创建时间。
    created_at: datetime = field(default_factory=utc_now)
