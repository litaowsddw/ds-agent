"""基于 LangGraph 的 Workflow DAG 执行器。

本模块只处理 Workflow DSL 到可执行 DAG 的映射，不依赖 FastAPI、数据库或
Celery。前端画布中的节点会被编译成 LangGraph 节点，画布连线会被编译成
LangGraph 边，因此用户可视化组装的结构就是后端实际执行结构。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

# LLMGatewayCall 是执行器调用 LLM 网关的函数签名。
LLMGatewayCall = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class WorkflowGraphState(TypedDict, total=False):
    """LangGraph 执行状态。

    workflow_input 保存本次运行的原始输入；context_by_node 保存每个节点的输出；
    node_runs 保存执行日志；failed/error_message 用于在节点失败后终止整体运行。
    """

    workflow_input: dict[str, Any]
    context_by_node: dict[str, dict[str, Any]]
    node_runs: list[ExecutedNode]
    failed: bool
    error_message: str


@dataclass(slots=True)
class ExecutedNode:
    """执行后的节点记录。"""

    # node_id 是工作流节点 ID，对应前端画布节点 ID。
    node_id: str

    # node_type 是节点类型，例如 start、llm、rag、tool、end。
    node_type: str

    # status 是节点执行状态，当前使用 succeeded/failed。
    status: str

    # input_data 是节点执行时接收到的上游输入。
    input_data: dict[str, Any]

    # output_data 是节点输出，后续节点会从 context_by_node 读取。
    output_data: dict[str, Any] = field(default_factory=dict)

    # error_message 是节点失败时的错误信息。
    error_message: str = ""

    # elapsed_ms 是节点耗时毫秒数。
    elapsed_ms: int = 0


@dataclass(slots=True)
class WorkflowExecutionResult:
    """工作流执行结果。"""

    # status 是整体执行状态。
    status: str

    # output_data 是最终输出，优先取 end 节点输出。
    output_data: dict[str, Any]

    # node_runs 是所有已执行节点的日志。
    node_runs: list[ExecutedNode]

    # error_message 是整体失败原因。
    error_message: str = ""


class WorkflowExecutor:
    """执行发布后的 Workflow DSL。"""

    def __init__(self, llm_gateway: LLMGatewayCall | None = None) -> None:
        """初始化执行器。

        参数：
            llm_gateway: LLM 节点调用入口。API 服务会注入真实 Gateway，单元测试或
                Worker 未注入时使用本地 mock fallback。
        """

        # llm_gateway 是 LLM 节点的唯一调用入口，避免执行器直接依赖具体供应商。
        self.llm_gateway = llm_gateway or self._mock_llm_gateway

    def execute(
        self, definition: dict[str, Any], input_data: dict[str, Any]
    ) -> WorkflowExecutionResult:
        """执行工作流定义。"""

        try:
            graph = self._compile_graph(definition=definition)
            final_state = graph.invoke(
                {
                    "workflow_input": input_data,
                    "context_by_node": {},
                    "node_runs": [],
                    "failed": False,
                    "error_message": "",
                }
            )
            node_runs = list(final_state.get("node_runs", []))
            error_message = str(final_state.get("error_message", ""))

            if final_state.get("failed"):
                return WorkflowExecutionResult(
                    status="failed",
                    output_data={},
                    node_runs=node_runs,
                    error_message=error_message,
                )

            return WorkflowExecutionResult(
                status="succeeded",
                output_data=self._final_output(executed_nodes=node_runs),
                node_runs=node_runs,
            )
        except Exception as exc:
            return WorkflowExecutionResult(
                status="failed",
                output_data={},
                node_runs=[],
                error_message=str(exc),
            )

    def _compile_graph(self, definition: dict[str, Any]):
        """把 Workflow DSL 编译成 LangGraph 可执行图。"""

        nodes_by_id = {str(node["id"]): node for node in definition.get("nodes", [])}
        if not nodes_by_id:
            raise ValueError("工作流至少需要一个节点")

        graph = StateGraph(WorkflowGraphState)
        definition_edges = [dict(edge) for edge in definition.get("edges", [])]
        for node_id, node in nodes_by_id.items():
            graph.add_node(
                node_id,
                self._build_langgraph_node(
                    node_id=node_id,
                    node=dict(node),
                    definition_edges=definition_edges,
                ),
            )

        incoming_count = {node_id: 0 for node_id in nodes_by_id}
        outgoing_count = {node_id: 0 for node_id in nodes_by_id}
        for edge in definition.get("edges", []):
            source = str(edge["source"])
            target = str(edge["target"])
            if source not in nodes_by_id or target not in nodes_by_id:
                raise ValueError(f"连线引用了不存在的节点：{source} -> {target}")
            graph.add_edge(source, target)
            incoming_count[target] += 1
            outgoing_count[source] += 1

        for node_id, count in incoming_count.items():
            if count == 0:
                graph.add_edge(START, node_id)

        for node_id, count in outgoing_count.items():
            if count == 0:
                graph.add_edge(node_id, END)

        return graph.compile()

    def _build_langgraph_node(
        self,
        node_id: str,
        node: dict[str, Any],
        definition_edges: list[dict[str, Any]],
    ):
        """构建单个 LangGraph 节点函数。"""

        node_type = str(node["type"])
        config = dict(node.get("config", {}))

        def run_node(state: WorkflowGraphState) -> dict[str, Any]:
            """执行 LangGraph 节点并把输出写回状态。"""

            if state.get("failed"):
                return {}

            context_by_node = dict(state.get("context_by_node", {}))
            node_runs = list(state.get("node_runs", []))
            node_input = self._build_node_input(
                definition_edges=definition_edges,
                node_id=node_id,
                input_data=dict(state.get("workflow_input", {})),
                context_by_node=context_by_node,
            )
            executed_node = self._execute_node(
                node_id=node_id,
                node_type=node_type,
                config=config,
                node_input=node_input,
            )
            node_runs.append(executed_node)

            if executed_node.status == "failed":
                return {
                    "node_runs": node_runs,
                    "failed": True,
                    "error_message": executed_node.error_message,
                }

            context_by_node[node_id] = executed_node.output_data
            return {"context_by_node": context_by_node, "node_runs": node_runs}

        return run_node

    def _execute_node(
        self,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> ExecutedNode:
        """执行单个节点。"""

        started_at = perf_counter()
        try:
            if node_type == "start":
                output_data = {"input": node_input.get("workflow_input", {})}
            elif node_type == "llm":
                output_data = self.llm_gateway(config, node_input)
            elif node_type == "rag":
                output_data = self._execute_rag_node(config=config, node_input=node_input)
            elif node_type == "tool":
                output_data = self._execute_tool_node(config=config, node_input=node_input)
            elif node_type == "end":
                output_data = {"result": node_input.get("upstream", {})}
            else:
                raise ValueError(f"不支持的节点类型：{node_type}")

            elapsed_ms = int((perf_counter() - started_at) * 1000)
            return ExecutedNode(
                node_id=node_id,
                node_type=node_type,
                status="succeeded",
                input_data=node_input,
                output_data=output_data,
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((perf_counter() - started_at) * 1000)
            return ExecutedNode(
                node_id=node_id,
                node_type=node_type,
                status="failed",
                input_data=node_input,
                error_message=str(exc),
                elapsed_ms=elapsed_ms,
            )

    def _build_node_input(
        self,
        definition_edges: list[dict[str, Any]],
        node_id: str,
        input_data: dict[str, Any],
        context_by_node: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """构建节点输入。"""

        upstream_node_ids = [
            str(edge["source"]) for edge in definition_edges if str(edge["target"]) == node_id
        ]
        upstream = {
            upstream_node_id: context_by_node.get(upstream_node_id, {})
            for upstream_node_id in upstream_node_ids
        }
        return {"workflow_input": input_data, "upstream": upstream}

    def _final_output(self, executed_nodes: list[ExecutedNode]) -> dict[str, Any]:
        """获取最终输出。"""

        for executed_node in reversed(executed_nodes):
            if executed_node.node_type == "end":
                return executed_node.output_data
        if not executed_nodes:
            return {}
        return executed_nodes[-1].output_data

    def _execute_rag_node(
        self, config: dict[str, Any], node_input: dict[str, Any]
    ) -> dict[str, Any]:
        """执行 RAG 节点的 MVP 占位逻辑。"""

        return {
            "query": node_input.get("workflow_input", {}),
            "collection": config.get("collection", "default"),
            "documents": [],
            "message": "RAG 节点已进入 LangGraph DAG，本轮使用空检索结果占位。",
            "upstream": node_input.get("upstream", {}),
        }

    def _execute_tool_node(
        self, config: dict[str, Any], node_input: dict[str, Any]
    ) -> dict[str, Any]:
        """执行 Tool 节点的 MVP 占位逻辑。"""

        return {
            "tool_name": config.get("tool_name", "unconfigured_tool"),
            "arguments": config.get("arguments", {}),
            "message": "Tool 节点已进入 LangGraph DAG，本轮未发起外部副作用调用。",
            "upstream": node_input.get("upstream", {}),
        }

    def _mock_llm_gateway(
        self, config: dict[str, Any], node_input: dict[str, Any]
    ) -> dict[str, Any]:
        """本地 mock LLM Gateway。"""

        prompt = str(config.get("prompt", ""))
        return {
            "text": f"[mock-llm] {prompt}".strip(),
            "provider": "mock",
            "model": str(config.get("model", "mock-model")),
            "upstream": node_input.get("upstream", {}),
            "usage": {
                "prompt_tokens": max(1, len(prompt) // 4),
                "completion_tokens": 8,
                "cache_hit_tokens": 0,
            },
        }
