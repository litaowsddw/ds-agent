"""Workflow variable-reference contract tests."""

import pytest

from packages.workflow.dsl import WorkflowDefinition, WorkflowEdge, WorkflowNode
from packages.workflow.executor import WorkflowExecutor
from packages.workflow.templates import WorkflowTemplateError, resolve_template_value
from packages.workflow.validator import WorkflowValidator


def test_template_resolves_input_and_node_output_with_native_tool_values() -> None:
    resolved = resolve_template_value(
        {
            "prompt": "客户 {{input.customer.name}} 的问题：{{retrieve.chunks.0.content}}",
            "arguments": {
                "customer_id": "{{input.customer.id}}",
                "chunks": "{{retrieve.chunks}}",
            },
        },
        variables={
            "input": {"customer": {"id": "cus-1", "name": "Ada"}},
            "retrieve": {"chunks": [{"content": "退款规则"}]},
        },
        location="节点 tool 的 config",
    )

    assert resolved == {
        "prompt": "客户 Ada 的问题：退款规则",
        "arguments": {
            "customer_id": "cus-1",
            "chunks": [{"content": "退款规则"}],
        },
    }


def test_template_rejects_malformed_and_missing_values() -> None:
    with pytest.raises(WorkflowTemplateError, match="未闭合"):
        resolve_template_value(
            "{{input.text", variables={"input": {"text": "hello"}}, location="config.prompt"
        )
    with pytest.raises(WorkflowTemplateError, match="字段 'missing' 不存在"):
        resolve_template_value(
            "{{input.missing}}", variables={"input": {"text": "hello"}}, location="config.prompt"
        )
    with pytest.raises(WorkflowTemplateError, match="变量 'other' 不存在"):
        resolve_template_value(
            "{{other.text}}", variables={"input": {"text": "hello"}}, location="config.prompt"
        )


def test_executor_maps_start_input_to_llm_prompt_and_llm_output_to_end() -> None:
    observed: dict[str, object] = {}

    def llm(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, object]:
        observed.update(config)
        return {"text": f"已处理：{config['prompt']}"}

    result = WorkflowExecutor(llm_gateway=llm).execute(
        {
            "nodes": [
                {"id": "start", "type": "start", "config": {}},
                {
                    "id": "answer",
                    "type": "llm",
                    "config": {"prompt": "回答用户问题：{{input.question}}"},
                },
                {"id": "end", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start", "target": "answer"},
                {"source": "answer", "target": "end"},
            ],
        },
        {"question": "如何退款？"},
    )

    assert result.status == "succeeded"
    assert observed["prompt"] == "回答用户问题：如何退款？"
    assert result.output_data == {
        "result": {"answer": {"text": "已处理：回答用户问题：如何退款？"}}
    }


def test_executor_maps_rag_output_to_tool_arguments() -> None:
    observed: dict[str, object] = {}

    def rag(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, object]:
        assert config["query_template"] == "退款"
        return {"chunks": [{"content": "退款需要提供订单号"}]}

    def tool(config: dict[str, object], _node_input: dict[str, object]) -> dict[str, object]:
        observed.update(config)
        return {"status": "planned"}

    result = WorkflowExecutor(rag_search=rag, tool_call=tool).execute(
        {
            "nodes": [
                {"id": "start", "type": "start", "config": {}},
                {
                    "id": "retrieve",
                    "type": "rag",
                    "config": {"query_template": "{{input.intent}}"},
                },
                {
                    "id": "create_ticket",
                    "type": "tool",
                    "config": {
                        "arguments": {
                            "subject": "{{input.subject}}",
                            "evidence": "{{retrieve.chunks.0.content}}",
                            "all_chunks": "{{retrieve.chunks}}",
                        }
                    },
                },
                {"id": "end", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start", "target": "retrieve"},
                {"source": "retrieve", "target": "create_ticket"},
                {"source": "create_ticket", "target": "end"},
            ],
        },
        {"intent": "退款", "subject": "订单退款"},
    )

    assert result.status == "succeeded"
    assert observed["arguments"] == {
        "subject": "订单退款",
        "evidence": "退款需要提供订单号",
        "all_chunks": [{"content": "退款需要提供订单号"}],
    }


def test_executor_fails_node_instead_of_silently_sending_unresolved_template() -> None:
    called = False

    def llm(_config: dict[str, object], _node_input: dict[str, object]) -> dict[str, object]:
        nonlocal called
        called = True
        return {"text": "must not run"}

    result = WorkflowExecutor(llm_gateway=llm).execute(
        {
            "nodes": [
                {"id": "start", "type": "start", "config": {}},
                {"id": "answer", "type": "llm", "config": {"prompt": "{{input.missing}}"}},
                {"id": "end", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "start", "target": "answer"},
                {"source": "answer", "target": "end"},
            ],
        },
        {"text": "hello"},
    )

    assert result.status == "failed"
    assert called is False
    assert result.node_runs[-1].node_id == "answer"
    assert "字段 'missing' 不存在" in result.error_message


def test_validator_rejects_unknown_or_non_upstream_node_references_before_publish() -> None:
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(node_id="left", node_type="llm", config={"provider": "p", "model": "m"}),
            WorkflowNode(node_id="right", node_type="llm", config={"provider": "p", "model": "m"}),
            WorkflowNode(
                node_id="end",
                node_type="end",
                config={"label": "{{right.text}} {{missing.text}}"},
            ),
        ],
        edges=[
            WorkflowEdge(source="start", target="left"),
            WorkflowEdge(source="start", target="right"),
            WorkflowEdge(source="left", target="end"),
            WorkflowEdge(source="right", target="end"),
        ],
    )

    result = WorkflowValidator().validate(workflow)

    assert result["valid"] is False
    errors = "\n".join(result["errors"])
    assert "不存在的节点输出" in errors
    assert "{{missing.text}}" in errors


def test_validator_rejects_reference_to_unconnected_branch() -> None:
    workflow = WorkflowDefinition(
        version="1.0",
        nodes=[
            WorkflowNode(node_id="start", node_type="start"),
            WorkflowNode(node_id="left", node_type="llm", config={"provider": "p", "model": "m"}),
            WorkflowNode(node_id="right", node_type="llm", config={"provider": "p", "model": "m"}),
            WorkflowNode(node_id="end", node_type="end", config={"label": "{{right.text}}"}),
        ],
        edges=[
            WorkflowEdge(source="start", target="left"),
            WorkflowEdge(source="start", target="right"),
            WorkflowEdge(source="left", target="end"),
            WorkflowEdge(source="right", target="end"),
        ],
    )

    # The graph above makes both nodes upstream of End, so it is valid.  The
    # stricter assertion below targets a reference from left to its sibling.
    workflow.nodes[1].config["prompt"] = "{{right.text}}"
    result = WorkflowValidator().validate(workflow)
    assert result["valid"] is False
    assert any("只能引用已连接上游节点" in error for error in result["errors"])
