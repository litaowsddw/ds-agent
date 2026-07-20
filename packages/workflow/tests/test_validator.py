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


def test_validator_rejects_disconnected_unconfigured_condition_node() -> None:
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(node_id="end", node_type="end"),
            WorkflowNode(node_id="condition", node_type="condition"),
        ],
        edges=[WorkflowEdge(source="start", target="end")],
    )

    result = WorkflowValidator().validate(workflow)

    assert result["valid"] is False
    assert any("condition" in error and "未连接" in error for error in result["errors"])
    assert any("condition" in error and "配置无效" in error for error in result["errors"])


def test_validator_accepts_safe_condition_with_two_named_branches() -> None:
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(
                node_id="check",
                node_type="condition",
                config={"left": "{{input.status}}", "operator": "equals", "value": "approved"},
            ),
            WorkflowNode(node_id="approved", node_type="end"),
        ],
        edges=[
            WorkflowEdge(source="start", target="check"),
            WorkflowEdge(source="check", target="approved", branch="true"),
            WorkflowEdge(source="check", target="approved", branch="false"),
        ],
    )

    result = WorkflowValidator().validate(workflow)

    assert result["valid"] is True


def test_validator_accepts_bounded_llm_reliability_policy() -> None:
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(
                node_id="draft",
                node_type="llm",
                config={
                    "provider": "openai",
                    "model": "gpt-test",
                    "reliability": {"max_attempts": 3, "timeout_seconds": 30},
                },
            ),
            WorkflowNode(node_id="end", node_type="end"),
        ],
        edges=[
            WorkflowEdge(source="start", target="draft"),
            WorkflowEdge(source="draft", target="end"),
        ],
    )

    result = WorkflowValidator().validate(workflow)

    assert result["valid"] is True


def test_validator_rejects_unsafe_or_side_effecting_reliability_policy() -> None:
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(
                node_id="call",
                node_type="tool",
                config={"tool_id": "send-email", "reliability": {"max_attempts": 2}},
            ),
            WorkflowNode(node_id="end", node_type="end"),
        ],
        edges=[
            WorkflowEdge(source="start", target="call"),
            WorkflowEdge(source="call", target="end"),
        ],
    )

    result = WorkflowValidator().validate(workflow)

    assert result["valid"] is False
    assert any("Tool/MCP" in error for error in result["errors"])


def test_validator_rejects_invalid_reliability_types_bounds_and_unknown_fields() -> None:
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(
                node_id="draft",
                node_type="llm",
                config={
                    "provider": "openai",
                    "model": "gpt-test",
                    "reliability": {
                        "max_attempts": True,
                        "timeout_seconds": 121,
                        "backoff_ms": 100,
                    },
                },
            ),
            WorkflowNode(node_id="end", node_type="end"),
        ],
        edges=[
            WorkflowEdge(source="start", target="draft"),
            WorkflowEdge(source="draft", target="end"),
        ],
    )

    result = WorkflowValidator().validate(workflow)

    assert result["valid"] is False
    assert any("backoff_ms" in error for error in result["errors"])


def test_validator_rejects_unsafe_condition_expression_and_missing_false_branch() -> None:
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(
                node_id="check",
                node_type="condition",
                config={"expression": "__import__('os').system('whoami')"},
            ),
            WorkflowNode(node_id="end", node_type="end"),
        ],
        edges=[
            WorkflowEdge(source="start", target="check"),
            WorkflowEdge(source="check", target="end", branch="true"),
        ],
    )

    result = WorkflowValidator().validate(workflow)

    assert result["valid"] is False
    assert any("配置无效" in error for error in result["errors"])
    assert any("false 出边" in error for error in result["errors"])
