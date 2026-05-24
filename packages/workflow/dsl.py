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


@dataclass(slots=True)
class WorkflowDefinition:
    """工作流定义。"""

    # version 是 DSL 版本，用于后续兼容升级。
    version: str

    # nodes 是节点列表。
    nodes: list[WorkflowNode]

    # edges 是连线列表。
    edges: list[WorkflowEdge]

