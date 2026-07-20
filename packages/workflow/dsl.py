"""Workflow DSL 数据结构。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkflowNode:
    """工作流节点。"""

    # node_id 是节点唯一标识，由前端画布生成并在发布后固定。
    node_id: str

    # node_type 表示节点类型，例如 start、llm、rag、tool、end。
    node_type: str

    # config 保存节点配置，具体 schema 由 node_type 决定。
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowEdge:
    """工作流边。"""

    # source 是起点节点 ID。
    source: str

    # target 是终点节点 ID。
    target: str

    # branch 为 Condition 节点的具名出边，仅允许 true 或 false。
    # 普通节点的连线必须保持为空，避免把路由语义悄悄附着到普通 DAG 边。
    branch: str | None = None


@dataclass(slots=True)
class WorkflowDefinition:
    """工作流定义。"""

    # version 是 DSL 版本，用于后续兼容升级。
    version: str

    # nodes 是节点列表。
    nodes: list[WorkflowNode]

    # edges 是连线列表。
    edges: list[WorkflowEdge]

    # execution_limits 是随发布版本冻结的运行保护策略。保留为原始对象，
    # 交给 budget 模块做严格校验，避免类型转换悄悄放宽用户设定的安全边界。
    execution_limits: object | None = None
