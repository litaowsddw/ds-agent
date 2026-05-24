"""Workflow 执行器。

该执行器只处理工作流定义、节点输入输出和执行顺序，不直接依赖 FastAPI、
数据库、Celery 或具体 LLM Provider。后续 Gateway、RAG、Tool、缓存都会从这里的
节点处理函数逐步接入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable


# LLMGatewayCall 是工作流执行器调用 LLM Gateway 的函数签名。
LLMGatewayCall = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class ExecutedNode:
    """执行后的节点记录。"""

    # node_id 是工作流节点 ID。
    node_id: str

    # node_type 是节点类型。
    node_type: str

    # status 是节点执行状态。
    status: str

    # input_data 是节点输入。
    input_data: dict[str, Any]

    # output_data 是节点输出。
    output_data: dict[str, Any] = field(default_factory=dict)

    # error_message 是节点失败时的错误信息。
    error_message: str = ""

    # elapsed_ms 是节点耗时毫秒。
    elapsed_ms: int = 0


@dataclass(slots=True)
class WorkflowExecutionResult:
    """工作流执行结果。"""

    # status 是整体执行状态。
    status: str

    # output_data 是最终输出。
    output_data: dict[str, Any]

    # node_runs 是节点执行记录。
    node_runs: list[ExecutedNode]

    # error_message 是整体失败原因。
    error_message: str = ""


class WorkflowExecutor:
    """执行发布后的 Workflow DSL。"""

    def __init__(self, llm_gateway: LLMGatewayCall | None = None) -> None:
        """初始化执行器。

        参数：
            llm_gateway: 可选 LLM 调用函数。API 服务会注入真实 Gateway；
                Worker 或单元测试未注入时使用本地 mock fallback。
        """

        # llm_gateway 是 LLM 节点的唯一调用入口，避免执行器直接依赖具体 Provider。
        self.llm_gateway = llm_gateway or self._mock_llm_gateway

    def execute(
        self,
        definition: dict[str, Any],
        input_data: dict[str, Any],
    ) -> WorkflowExecutionResult:
        """执行工作流定义。

        参数：
            definition: 已发布且通过校验的 Workflow DSL。
            input_data: 本次运行输入。
        """

        # nodes_by_id 是节点 ID 到节点定义的索引。
        nodes_by_id = {str(node["id"]): node for node in definition.get("nodes", [])}

        # execution_order 是拓扑排序后的节点执行顺序。
        execution_order = self._topological_order(definition=definition)

        # context_by_node 保存每个节点输出，后续节点可以从中读取上游结果。
        context_by_node: dict[str, dict[str, Any]] = {}

        # executed_nodes 保存节点执行记录。
        executed_nodes: list[ExecutedNode] = []

        try:
            for node_id in execution_order:
                node = nodes_by_id[node_id]
                node_type = str(node["type"])
                node_input = self._build_node_input(
                    definition=definition,
                    node_id=node_id,
                    input_data=input_data,
                    context_by_node=context_by_node,
                )
                executed_node = self._execute_node(
                    node_id=node_id,
                    node_type=node_type,
                    config=dict(node.get("config", {})),
                    node_input=node_input,
                )
                executed_nodes.append(executed_node)
                context_by_node[node_id] = executed_node.output_data

            # final_output 优先使用 end 节点输出；不存在时返回最后一个节点输出。
            final_output = self._final_output(executed_nodes=executed_nodes)
            return WorkflowExecutionResult(
                status="succeeded",
                output_data=final_output,
                node_runs=executed_nodes,
            )
        except Exception as exc:
            return WorkflowExecutionResult(
                status="failed",
                output_data={},
                node_runs=executed_nodes,
                error_message=str(exc),
            )

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
        definition: dict[str, Any],
        node_id: str,
        input_data: dict[str, Any],
        context_by_node: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """构建节点输入。"""

        # upstream_node_ids 是当前节点的所有上游节点。
        upstream_node_ids = [
            str(edge["source"])
            for edge in definition.get("edges", [])
            if str(edge["target"]) == node_id
        ]

        # upstream 保存上游节点输出。
        upstream = {
            upstream_node_id: context_by_node.get(upstream_node_id, {})
            for upstream_node_id in upstream_node_ids
        }

        return {"workflow_input": input_data, "upstream": upstream}

    def _topological_order(self, definition: dict[str, Any]) -> list[str]:
        """对工作流节点做拓扑排序。"""

        node_ids = [str(node["id"]) for node in definition.get("nodes", [])]

        # indegree 保存每个节点入度。
        indegree = {node_id: 0 for node_id in node_ids}

        # adjacency 保存邻接表。
        adjacency = {node_id: [] for node_id in node_ids}

        for edge in definition.get("edges", []):
            source = str(edge["source"])
            target = str(edge["target"])
            adjacency[source].append(target)
            indegree[target] += 1

        # ready 保存当前可以执行的节点，按 ID 排序保证稳定执行顺序。
        ready = sorted([node_id for node_id, value in indegree.items() if value == 0])
        order: list[str] = []

        while ready:
            node_id = ready.pop(0)
            order.append(node_id)
            for next_node_id in sorted(adjacency[node_id]):
                indegree[next_node_id] -= 1
                if indegree[next_node_id] == 0:
                    ready.append(next_node_id)
                    ready.sort()

        if len(order) != len(node_ids):
            raise ValueError("工作流包含环或不可达节点，无法执行")

        return order

    def _final_output(self, executed_nodes: list[ExecutedNode]) -> dict[str, Any]:
        """获取最终输出。"""

        for executed_node in reversed(executed_nodes):
            if executed_node.node_type == "end":
                return executed_node.output_data

        if not executed_nodes:
            return {}

        return executed_nodes[-1].output_data

    def _mock_llm_gateway(
        self,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> dict[str, Any]:
        """本地 mock LLM Gateway。

        该 fallback 只用于 Worker 未注入 Gateway 或单元测试场景。生产 API 执行路径会
        注入 `apps.api.app.gateway.llm.LLMGateway`。
        """

        # prompt 是 LLM 节点配置中的提示词。
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
