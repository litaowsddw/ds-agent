"""WorkflowValidator 测试。"""

from packages.workflow.dsl import WorkflowDefinition, WorkflowEdge, WorkflowNode
from packages.workflow.validator import WorkflowValidator


def test_validator_accepts_start_to_end_workflow() -> None:
    """Start -> End 的最小工作流应该通过校验。"""

    # workflow 是 MVP 阶段最小合法工作流定义。
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(node_id="end", node_type="end"),
        ],
        edges=[WorkflowEdge(source="start", target="end")],
    )

    # validator 是被测 DAG 校验器。
    validator = WorkflowValidator()

    result = validator.validate(workflow)

    assert result["valid"] is True
    assert result["errors"] == []


def test_validator_rejects_missing_end_node() -> None:
    """缺少 End 节点的工作流不能发布。"""

    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[WorkflowNode(node_id="start", node_type="start")],
        edges=[],
    )

    validator = WorkflowValidator()
    result = validator.validate(workflow)

    assert result["valid"] is False
    assert "工作流必须包含 end 节点" in result["errors"]

