"""基于 LangGraph 的 Workflow DAG 执行器。

执行器只负责把前端 DSL 编译成可执行图，不直接依赖 FastAPI 路由。
LLM、RAG、Tool 节点的真实能力由上层注入，因此生产链路不会再返回内置 mock 数据。
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

NodeCallResult = dict[str, Any] | Awaitable[dict[str, Any]]

# LLMGatewayCall 是 LLM 节点的真实调用入口。
LLMGatewayCall = Callable[[dict[str, Any], dict[str, Any]], NodeCallResult]

# RAGNodeCall 是 RAG 节点的真实检索入口。
RAGNodeCall = Callable[[dict[str, Any], dict[str, Any]], NodeCallResult]

# ToolNodeCall 是 Tool 节点的真实工具授权与调用入口。
ToolNodeCall = Callable[[dict[str, Any], dict[str, Any]], NodeCallResult]


class WorkflowGraphState(TypedDict, total=False):
    """LangGraph 执行状态。"""

    workflow_input: dict[str, Any]
    context_by_node: dict[str, dict[str, Any]]
    node_runs: list["ExecutedNode"]
    failed: bool
    error_message: str


@dataclass(slots=True)
class ExecutedNode:
    """单个节点执行结果。"""

    # node_id 对应前端画布节点 ID。
    node_id: str

    # node_type 表示节点类型，例如 start、llm、rag、tool、end。
    node_type: str

    # status 使用 succeeded 或 failed。
    status: str

    # input_data 是节点执行时收到的工作流输入与上游输出。
    input_data: dict[str, Any]

    # output_data 是节点输出，会传递给后续节点。
    output_data: dict[str, Any] = field(default_factory=dict)

    # error_message 保存节点失败原因。
    error_message: str = ""

    # elapsed_ms 是节点耗时毫秒数。
    elapsed_ms: int = 0


@dataclass(slots=True)
class WorkflowExecutionResult:
    """工作流执行结果。"""

    # status 是整体执行状态。
    status: str

    # output_data 是最终输出，优先取 End 节点输出。
    output_data: dict[str, Any]

    # node_runs 保存全部已执行节点日志。
    node_runs: list[ExecutedNode]

    # error_message 保存整体失败原因。
    error_message: str = ""


class WorkflowExecutor:
    """执行发布后的 Workflow DSL。"""

    def __init__(
        self,
        llm_gateway: LLMGatewayCall | None = None,
        rag_search: RAGNodeCall | None = None,
        tool_call: ToolNodeCall | None = None,
    ) -> None:
        """初始化执行器。

        生产环境必须注入真实的 LLM、RAG、Tool 执行函数。没有注入时，相关节点会失败，
        这样前端和用户不会误以为占位数据是真实执行结果。
        """

        self.llm_gateway = llm_gateway
        self.rag_search = rag_search
        self.tool_call = tool_call

    def execute(
        self, definition: dict[str, Any], input_data: dict[str, Any]
    ) -> WorkflowExecutionResult:
        """同步执行工作流。

        该入口只支持同步注入函数，主要用于不需要数据库异步上下文的单元测试。
        API 路由中的真实执行使用 execute_async。
        """

        try:
            graph = self._compile_graph(definition=definition, async_mode=False)
            final_state = graph.invoke(self._initial_state(input_data))
            return self._to_result(final_state)
        except Exception as exc:
            return WorkflowExecutionResult(
                status="failed",
                output_data={},
                node_runs=[],
                error_message=str(exc),
            )

    async def execute_async(
        self, definition: dict[str, Any], input_data: dict[str, Any]
    ) -> WorkflowExecutionResult:
        """异步执行工作流。

        真实接口会在这里注入数据库、模型供应商、知识库和 MCP 授权能力。
        """

        try:
            graph = self._compile_graph(async_mode=True, definition=definition)
            final_state = await graph.ainvoke(self._initial_state(input_data))
            return self._to_result(final_state)
        except Exception as exc:
            return WorkflowExecutionResult(
                status="failed",
                output_data={},
                node_runs=[],
                error_message=str(exc),
            )

    def _compile_graph(self, definition: dict[str, Any] | None = None, async_mode: bool = False):
        """把 Workflow DSL 编译成 LangGraph 可执行图。"""

        definition = definition or {}
        nodes_by_id = {str(node["id"]): node for node in definition.get("nodes", [])}
        if not nodes_by_id:
            raise ValueError("工作流至少需要一个节点")

        graph = StateGraph(WorkflowGraphState)
        definition_edges = [dict(edge) for edge in definition.get("edges", [])]
        for node_id, node in nodes_by_id.items():
            node_builder = self._build_async_langgraph_node if async_mode else self._build_sync_langgraph_node
            graph.add_node(
                node_id,
                node_builder(
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

    def _build_sync_langgraph_node(
        self,
        node_id: str,
        node: dict[str, Any],
        definition_edges: list[dict[str, Any]],
    ):
        """构建同步 LangGraph 节点函数。"""

        node_type = str(node["type"])
        config = dict(node.get("config", {}))

        def run_node(state: WorkflowGraphState) -> dict[str, Any]:
            if state.get("failed"):
                return {}
            return self._run_sync_node(
                state=state,
                node_id=node_id,
                node_type=node_type,
                config=config,
                definition_edges=definition_edges,
            )

        return run_node

    def _build_async_langgraph_node(
        self,
        node_id: str,
        node: dict[str, Any],
        definition_edges: list[dict[str, Any]],
    ):
        """构建异步 LangGraph 节点函数。"""

        node_type = str(node["type"])
        config = dict(node.get("config", {}))

        async def run_node(state: WorkflowGraphState) -> dict[str, Any]:
            if state.get("failed"):
                return {}
            return await self._run_async_node(
                state=state,
                node_id=node_id,
                node_type=node_type,
                config=config,
                definition_edges=definition_edges,
            )

        return run_node

    def _run_sync_node(
        self,
        state: WorkflowGraphState,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        definition_edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """执行同步节点并更新状态。"""

        context_by_node = dict(state.get("context_by_node", {}))
        node_runs = list(state.get("node_runs", []))
        node_input = self._build_node_input(
            definition_edges=definition_edges,
            node_id=node_id,
            input_data=dict(state.get("workflow_input", {})),
            context_by_node=context_by_node,
        )
        executed_node = self._execute_node_sync(node_id, node_type, config, node_input)
        return self._merge_node_result(node_id, context_by_node, node_runs, executed_node)

    async def _run_async_node(
        self,
        state: WorkflowGraphState,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        definition_edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """执行异步节点并更新状态。"""

        context_by_node = dict(state.get("context_by_node", {}))
        node_runs = list(state.get("node_runs", []))
        node_input = self._build_node_input(
            definition_edges=definition_edges,
            node_id=node_id,
            input_data=dict(state.get("workflow_input", {})),
            context_by_node=context_by_node,
        )
        executed_node = await self._execute_node_async(node_id, node_type, config, node_input)
        return self._merge_node_result(node_id, context_by_node, node_runs, executed_node)

    def _execute_node_sync(
        self,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> ExecutedNode:
        """同步执行单个节点。"""

        started_at = perf_counter()
        try:
            output_data = self._resolve_sync_output(node_type, config, node_input)
            return self._succeeded_node(node_id, node_type, node_input, output_data, started_at)
        except Exception as exc:
            return self._failed_node(node_id, node_type, node_input, exc, started_at)

    async def _execute_node_async(
        self,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> ExecutedNode:
        """异步执行单个节点。"""

        started_at = perf_counter()
        try:
            output_data = await self._resolve_async_output(node_type, config, node_input)
            return self._succeeded_node(node_id, node_type, node_input, output_data, started_at)
        except Exception as exc:
            return self._failed_node(node_id, node_type, node_input, exc, started_at)

    def _resolve_sync_output(
        self, node_type: str, config: dict[str, Any], node_input: dict[str, Any]
    ) -> dict[str, Any]:
        """解析同步节点输出。"""

        if node_type == "start":
            return {"input": node_input.get("workflow_input", {})}
        if node_type == "end":
            return {"result": node_input.get("upstream", {})}
        call = self._required_call(node_type)
        output = call(config, node_input)
        if inspect.isawaitable(output):
            raise RuntimeError(f"{node_type} 节点注入了异步函数，请使用 execute_async")
        return dict(output)

    async def _resolve_async_output(
        self, node_type: str, config: dict[str, Any], node_input: dict[str, Any]
    ) -> dict[str, Any]:
        """解析异步节点输出。"""

        if node_type == "start":
            return {"input": node_input.get("workflow_input", {})}
        if node_type == "end":
            return {"result": node_input.get("upstream", {})}
        call = self._required_call(node_type)
        output = call(config, node_input)
        if inspect.isawaitable(output):
            output = await output
        return dict(output)

    def _required_call(self, node_type: str) -> LLMGatewayCall | RAGNodeCall | ToolNodeCall:
        """读取节点真实执行函数，缺失时直接失败。"""

        if node_type == "llm" and self.llm_gateway is not None:
            return self.llm_gateway
        if node_type == "rag" and self.rag_search is not None:
            return self.rag_search
        if node_type == "tool" and self.tool_call is not None:
            return self.tool_call
        raise ValueError(f"{node_type} 节点没有配置真实执行器")

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

    def _merge_node_result(
        self,
        node_id: str,
        context_by_node: dict[str, dict[str, Any]],
        node_runs: list[ExecutedNode],
        executed_node: ExecutedNode,
    ) -> dict[str, Any]:
        """把单节点结果合并回 LangGraph 状态。"""

        node_runs.append(executed_node)
        if executed_node.status == "failed":
            return {
                "node_runs": node_runs,
                "failed": True,
                "error_message": executed_node.error_message,
            }
        context_by_node[node_id] = executed_node.output_data
        return {"context_by_node": context_by_node, "node_runs": node_runs}

    def _final_output(self, executed_nodes: list[ExecutedNode]) -> dict[str, Any]:
        """获取最终输出。"""

        for executed_node in reversed(executed_nodes):
            if executed_node.node_type == "end":
                return executed_node.output_data
        if not executed_nodes:
            return {}
        return executed_nodes[-1].output_data

    def _initial_state(self, input_data: dict[str, Any]) -> WorkflowGraphState:
        """创建 LangGraph 初始状态。"""

        return {
            "workflow_input": input_data,
            "context_by_node": {},
            "node_runs": [],
            "failed": False,
            "error_message": "",
        }

    def _to_result(self, final_state: WorkflowGraphState) -> WorkflowExecutionResult:
        """把 LangGraph 终态转换成 API 友好的结果对象。"""

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

    def _succeeded_node(
        self,
        node_id: str,
        node_type: str,
        node_input: dict[str, Any],
        output_data: dict[str, Any],
        started_at: float,
    ) -> ExecutedNode:
        """创建成功节点记录。"""

        return ExecutedNode(
            node_id=node_id,
            node_type=node_type,
            status="succeeded",
            input_data=node_input,
            output_data=output_data,
            elapsed_ms=int((perf_counter() - started_at) * 1000),
        )

    def _failed_node(
        self,
        node_id: str,
        node_type: str,
        node_input: dict[str, Any],
        exc: Exception,
        started_at: float,
    ) -> ExecutedNode:
        """创建失败节点记录。"""

        return ExecutedNode(
            node_id=node_id,
            node_type=node_type,
            status="failed",
            input_data=node_input,
            error_message=str(exc),
            elapsed_ms=int((perf_counter() - started_at) * 1000),
        )
