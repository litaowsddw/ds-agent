"""基于 LangGraph 的 Workflow DAG 执行器。

执行器只负责把前端 DSL 编译成可执行图，不直接依赖 FastAPI 路由。
LLM、RAG、Tool 节点的真实能力由上层注入，因此生产链路不会再返回内置 mock 数据。
"""

from __future__ import annotations

import asyncio
import inspect
from contextvars import ContextVar
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from packages.workflow.conditions import evaluate_condition, normalize_condition_config
from packages.workflow.budget import (
    WorkflowBudgetGuard,
    execution_limits_from_definition,
)
from packages.workflow.reliability import (
    NodeReliabilityPolicy,
    WorkflowNodeTimeout,
    WorkflowSyncTimeoutUnsupported,
    is_retryable_node_error,
    reliability_policy_for_node,
    strip_reliability_policy,
)
from packages.workflow.templates import resolve_template_value

NodeCallResult = dict[str, Any] | Awaitable[dict[str, Any]]


def _edge_branch(edge: dict[str, Any]) -> str | None:
    """Read the canonical branch field and two React Flow compatibility names."""

    value = edge.get("branch", edge.get("source_handle", edge.get("sourceHandle")))
    if value is None:
        return None
    return str(value).strip()


def _merge_context_by_node(
    current: dict[str, dict[str, Any]] | None,
    update: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Merge outputs produced by independent branches in the same graph step."""

    return {**(current or {}), **(update or {})}


def _append_node_runs(
    current: list["ExecutedNode"] | None,
    update: list["ExecutedNode"] | None,
) -> list["ExecutedNode"]:
    """Append only the node runs produced by the current graph step."""

    return [*(current or []), *(update or [])]


def _any_failed(current: bool | None, update: bool | None) -> bool:
    """Keep a workflow failed once any branch has failed."""

    return bool(current) or bool(update)


def _first_error(current: str | None, update: str | None) -> str:
    """Preserve the first concrete branch failure for the run summary."""

    return current or update or ""

# LLMGatewayCall 是 LLM 节点的真实调用入口。
LLMGatewayCall = Callable[[dict[str, Any], dict[str, Any]], NodeCallResult]

# RAGNodeCall 是 RAG 节点的真实检索入口。
RAGNodeCall = Callable[[dict[str, Any], dict[str, Any]], NodeCallResult]

# ToolNodeCall 是 Tool 节点的真实工具授权与调用入口。
ToolNodeCall = Callable[[dict[str, Any], dict[str, Any]], NodeCallResult]


class WorkflowApprovalRequired(Exception):
    """A reviewed Tool invocation was persisted and is awaiting a decision.

    This is an execution control signal, not an error.  Keeping it in the
    workflow package lets application integrations pause a graph without
    importing API/database code into the generic executor.
    """

    def __init__(self, approval_id: str, message: str) -> None:
        super().__init__(message)
        self.approval_id = approval_id


class _NodeAttemptFailure(Exception):
    """Carry an external callback's terminal error and real attempt count."""

    def __init__(self, cause: Exception, attempt_count: int) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.attempt_count = attempt_count


class WorkflowGraphState(TypedDict, total=False):
    """LangGraph 执行状态。"""

    workflow_input: dict[str, Any]
    context_by_node: Annotated[
        dict[str, dict[str, Any]], _merge_context_by_node
    ]
    node_runs: Annotated[list["ExecutedNode"], _append_node_runs]
    failed: Annotated[bool, _any_failed]
    error_message: Annotated[str, _first_error]
    waiting_approval: bool


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

    # Actual provider attempts. This remains zero when a pre-call budget or
    # configuration check rejects an external node before it is invoked.
    attempt_count: int = 1

    # The terminal callback error without retry decoration, for trace viewers.
    last_error: str = ""


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
        # A ContextVar keeps one mutable counter isolated per execute/execute_async
        # call, including concurrent runs using the same executor instance.
        self._budget_guard: ContextVar[WorkflowBudgetGuard | None] = ContextVar(
            "workflow_budget_guard", default=None
        )

    def execute(
        self, definition: dict[str, Any], input_data: dict[str, Any]
    ) -> WorkflowExecutionResult:
        """同步执行工作流。

        该入口只支持同步注入函数，主要用于不需要数据库异步上下文的单元测试。
        API 路由中的真实执行使用 execute_async。
        """

        guard_token = self._budget_guard.set(
            WorkflowBudgetGuard(execution_limits_from_definition(definition))
        )
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
        finally:
            self._budget_guard.reset(guard_token)

    async def execute_async(
        self,
        definition: dict[str, Any],
        input_data: dict[str, Any],
        *,
        resume_state: dict[str, dict[str, Any]] | None = None,
        completed_node_ids: set[str] | None = None,
    ) -> WorkflowExecutionResult:
        """异步执行工作流。

        真实接口会在这里注入数据库、模型供应商、知识库和 MCP 授权能力。

        ``resume_state`` / ``completed_node_ids`` 用于审批后 DAG 续跑：把
        已成功节点的输出预置进 ``context_by_node``，并跳过这些节点的重复执行，
        从而只运行暂停点之后的下游节点而不会重放成功过的外部动作。
        """

        guard_token = self._budget_guard.set(
            WorkflowBudgetGuard(execution_limits_from_definition(definition))
        )
        try:
            graph = self._compile_graph(
                async_mode=True,
                definition=definition,
                completed_node_ids=completed_node_ids or set(),
            )
            final_state = await graph.ainvoke(self._initial_state(input_data, resume_state=resume_state))
            return self._to_result(final_state)
        except Exception as exc:
            return WorkflowExecutionResult(
                status="failed",
                output_data={},
                node_runs=[],
                error_message=str(exc),
            )
        finally:
            self._budget_guard.reset(guard_token)

    def _compile_graph(
        self,
        definition: dict[str, Any] | None = None,
        async_mode: bool = False,
        completed_node_ids: set[str] | None = None,
    ):
        """把 Workflow DSL 编译成 LangGraph 可执行图。"""

        definition = definition or {}
        nodes_by_id = {str(node["id"]): node for node in definition.get("nodes", [])}
        if not nodes_by_id:
            raise ValueError("工作流至少需要一个节点")

        graph = StateGraph(WorkflowGraphState)
        definition_edges = [dict(edge) for edge in definition.get("edges", [])]
        completed_node_ids = completed_node_ids or set()
        for node_id, node in nodes_by_id.items():
            node_builder = self._build_async_langgraph_node if async_mode else self._build_sync_langgraph_node
            graph.add_node(
                node_id,
                node_builder(
                    node_id=node_id,
                    node=dict(node),
                    definition_edges=definition_edges,
                    skip=node_id in completed_node_ids,
                ),
            )

        incoming_count = {node_id: 0 for node_id in nodes_by_id}
        outgoing_count = {node_id: 0 for node_id in nodes_by_id}
        condition_branch_targets: dict[str, dict[str, str]] = {}
        for edge in definition.get("edges", []):
            source = str(edge["source"])
            target = str(edge["target"])
            if source not in nodes_by_id or target not in nodes_by_id:
                raise ValueError(f"连线引用了不存在的节点：{source} -> {target}")
            if str(nodes_by_id[source].get("type")) == "condition":
                branch = _edge_branch(edge)
                if branch not in {"true", "false"}:
                    raise ValueError(f"条件节点 {source} 的出边必须声明 true 或 false branch")
                if branch in condition_branch_targets.setdefault(source, {}):
                    raise ValueError(f"条件节点 {source} 存在重复的 {branch} 出边")
                condition_branch_targets[source][branch] = target
            else:
                graph.add_edge(source, target)
            incoming_count[target] += 1
            outgoing_count[source] += 1

        for node_id, node in nodes_by_id.items():
            if str(node.get("type")) != "condition":
                continue
            targets = condition_branch_targets.get(node_id, {})
            if set(targets) != {"true", "false"}:
                raise ValueError(f"条件节点 {node_id} 必须同时配置 true 和 false 出边")
            graph.add_conditional_edges(
                node_id,
                self._condition_router(node_id),
                {"true": targets["true"], "false": targets["false"]},
            )

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
        skip: bool = False,
    ):
        """构建同步 LangGraph 节点函数。"""

        node_type = str(node["type"])
        config = dict(node.get("config", {}))

        def run_node(state: WorkflowGraphState) -> dict[str, Any]:
            if skip or state.get("failed") or state.get("waiting_approval"):
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
        skip: bool = False,
    ):
        """构建异步 LangGraph 节点函数。"""

        node_type = str(node["type"])
        config = dict(node.get("config", {}))

        async def run_node(state: WorkflowGraphState) -> dict[str, Any]:
            if skip or state.get("failed") or state.get("waiting_approval"):
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
        node_input = self._build_node_input(
            definition_edges=definition_edges,
            node_id=node_id,
            input_data=dict(state.get("workflow_input", {})),
            context_by_node=context_by_node,
        )
        executed_node = self._execute_node_sync(node_id, node_type, config, node_input)
        return self._merge_node_result(node_id, executed_node)

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
        node_input = self._build_node_input(
            definition_edges=definition_edges,
            node_id=node_id,
            input_data=dict(state.get("workflow_input", {})),
            context_by_node=context_by_node,
        )
        # The node ID is owned by the validated workflow definition, not by
        # caller-controlled node output or tool configuration.
        callback_config = {**config, "id": node_id}
        executed_node = await self._execute_node_async(
            node_id, node_type, callback_config, node_input
        )
        return self._merge_node_result(node_id, executed_node)

    def _execute_node_sync(
        self,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> ExecutedNode:
        """同步执行单个节点。"""

        started_at = perf_counter()
        policy = NodeReliabilityPolicy()
        attempt_count = 0 if node_type in {"llm", "rag"} else 1
        try:
            self._consume_execution_budget(node_type)
            policy = reliability_policy_for_node(node_type, config)
            if node_type == "condition":
                config = normalize_condition_config(config)
            resolved_config = self._resolve_node_config(node_id, config, node_input)
            callback_config = strip_reliability_policy(resolved_config)
            if node_type in {"llm", "rag"}:
                if policy.timeout_seconds is not None:
                    raise WorkflowSyncTimeoutUnsupported(
                        "同步 execute 无法安全终止阻塞的外部调用；"
                        "配置 reliability.timeout_seconds 时请使用 execute_async"
                    )
                output_data, attempt_count = self._resolve_retrying_sync_output(
                    node_type,
                    callback_config,
                    node_input,
                    policy,
                )
            else:
                output_data = self._resolve_sync_output(
                    node_type, callback_config, node_input
                )
            return self._succeeded_node(
                node_id,
                node_type,
                node_input,
                output_data,
                started_at,
                attempt_count=attempt_count,
            )
        except _NodeAttemptFailure as failure:
            return self._failed_node(
                node_id,
                node_type,
                node_input,
                failure.cause,
                started_at,
                attempt_count=failure.attempt_count,
                max_attempts=policy.max_attempts,
            )
        except WorkflowApprovalRequired as exc:
            return self._waiting_approval_node(node_id, node_type, node_input, exc, started_at)
        except Exception as exc:
            return self._failed_node(
                node_id,
                node_type,
                node_input,
                exc,
                started_at,
                attempt_count=attempt_count,
                max_attempts=policy.max_attempts,
            )

    async def _execute_node_async(
        self,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> ExecutedNode:
        """异步执行单个节点。"""

        started_at = perf_counter()
        policy = NodeReliabilityPolicy()
        attempt_count = 0 if node_type in {"llm", "rag"} else 1
        try:
            self._consume_execution_budget(node_type)
            policy = reliability_policy_for_node(node_type, config)
            if node_type == "condition":
                config = normalize_condition_config(config)
            resolved_config = self._resolve_node_config(node_id, config, node_input)
            callback_config = strip_reliability_policy(resolved_config)
            if node_type in {"llm", "rag"}:
                output_data, attempt_count = await self._resolve_retrying_async_output(
                    node_type,
                    callback_config,
                    node_input,
                    policy,
                )
            else:
                output_data = await self._resolve_async_output(
                    node_type, callback_config, node_input
                )
            return self._succeeded_node(
                node_id,
                node_type,
                node_input,
                output_data,
                started_at,
                attempt_count=attempt_count,
            )
        except _NodeAttemptFailure as failure:
            return self._failed_node(
                node_id,
                node_type,
                node_input,
                failure.cause,
                started_at,
                attempt_count=failure.attempt_count,
                max_attempts=policy.max_attempts,
            )
        except WorkflowApprovalRequired as exc:
            return self._waiting_approval_node(node_id, node_type, node_input, exc, started_at)
        except Exception as exc:
            return self._failed_node(
                node_id,
                node_type,
                node_input,
                exc,
                started_at,
                attempt_count=attempt_count,
                max_attempts=policy.max_attempts,
            )

    def _consume_execution_budget(self, node_type: str) -> None:
        """Reserve this node before resolving config or invoking an external service."""

        guard = self._budget_guard.get()
        if guard is not None:
            guard.before_node(node_type)

    def _consume_external_attempt_budget(self, node_type: str) -> None:
        """Reserve every actual LLM provider attempt, including retries."""

        guard = self._budget_guard.get()
        if guard is not None and node_type == "llm":
            guard.before_llm_attempt()

    def _resolve_retrying_sync_output(
        self,
        node_type: str,
        config: dict[str, Any],
        node_input: dict[str, Any],
        policy: NodeReliabilityPolicy,
    ) -> tuple[dict[str, Any], int]:
        """Retry completed retryable LLM/RAG failures in the sync test path.

        A synchronous Python callback cannot be forcibly and safely stopped.
        Callers with an explicit timeout policy are rejected before reaching
        this method; production integrations use ``execute_async`` instead.
        """

        attempt_count = 0
        while attempt_count < policy.max_attempts:
            try:
                self._consume_external_attempt_budget(node_type)
            except Exception as exc:
                raise _NodeAttemptFailure(exc, attempt_count) from exc
            attempt_count += 1
            try:
                return (
                    self._resolve_sync_output(node_type, config, node_input),
                    attempt_count,
                )
            except WorkflowApprovalRequired:
                raise
            except Exception as exc:
                if attempt_count >= policy.max_attempts or not is_retryable_node_error(exc):
                    raise _NodeAttemptFailure(exc, attempt_count) from exc
        raise AssertionError("retry loop must return or raise")  # pragma: no cover

    async def _resolve_retrying_async_output(
        self,
        node_type: str,
        config: dict[str, Any],
        node_input: dict[str, Any],
        policy: NodeReliabilityPolicy,
    ) -> tuple[dict[str, Any], int]:
        """Run bounded async retries without retrying client-side timeouts."""

        timeout_seconds = policy.async_timeout_seconds()
        attempt_count = 0
        while attempt_count < policy.max_attempts:
            try:
                self._consume_external_attempt_budget(node_type)
            except Exception as exc:
                raise _NodeAttemptFailure(exc, attempt_count) from exc
            attempt_count += 1
            try:
                output_data = await asyncio.wait_for(
                    self._resolve_async_output(node_type, config, node_input),
                    timeout=timeout_seconds,
                )
                return output_data, attempt_count
            except TimeoutError as exc:
                # ``wait_for`` stops this workflow from waiting. A blocking
                # synchronous integration may itself finish later, so retrying
                # here could duplicate provider work and token charges.
                timeout_error = WorkflowNodeTimeout(
                    f"{node_type} 节点等待外部服务超过 {timeout_seconds} 秒，已停止等待"
                )
                raise _NodeAttemptFailure(timeout_error, attempt_count) from exc
            except WorkflowApprovalRequired:
                raise
            except Exception as exc:
                if attempt_count >= policy.max_attempts or not is_retryable_node_error(exc):
                    raise _NodeAttemptFailure(exc, attempt_count) from exc
        raise AssertionError("retry loop must return or raise")  # pragma: no cover

    def _resolve_sync_output(
        self, node_type: str, config: dict[str, Any], node_input: dict[str, Any]
    ) -> dict[str, Any]:
        """解析同步节点输出。"""

        if node_type == "start":
            return {"input": node_input.get("workflow_input", {})}
        if node_type == "end":
            return {"result": node_input.get("upstream", {})}
        if node_type == "condition":
            matched = evaluate_condition(config)
            return {"result": matched, "branch": "true" if matched else "false"}
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
        if node_type == "condition":
            matched = evaluate_condition(config)
            return {"result": matched, "branch": "true" if matched else "false"}
        call = self._required_call(node_type)
        # The callback construction runs off the event loop so the enclosing
        # ``asyncio.wait_for`` can stop waiting on a blocking synchronous
        # integration. A returned coroutine is awaited on this event loop.
        output = await asyncio.to_thread(call, config, node_input)
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
        # ``variables`` is the data contract exposed to templates in node
        # config.  Node IDs form namespaces for their output fields, while
        # ``input`` is a concise alias for the workflow invocation payload.
        # The executor never exposes Python objects or evaluators here.
        variables = {
            **context_by_node,
            "input": input_data,
            "workflow_input": input_data,
            "upstream": upstream,
        }
        return {
            "workflow_input": input_data,
            "upstream": upstream,
            "variables": variables,
        }

    def _resolve_node_config(
        self,
        node_id: str,
        config: dict[str, Any],
        node_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve only the data-only template language before node execution."""

        variables = node_input.get("variables")
        if not isinstance(variables, dict):
            raise ValueError(f"节点 {node_id} 缺少模板变量上下文")
        resolved = resolve_template_value(
            config,
            variables=variables,
            location=f"节点 {node_id} 的 config",
        )
        if not isinstance(resolved, dict):  # ``config`` is a validated object.
            raise ValueError(f"节点 {node_id} 的 config 模板解析后必须是对象")
        return resolved

    def _merge_node_result(
        self,
        node_id: str,
        executed_node: ExecutedNode,
    ) -> dict[str, Any]:
        """把单节点结果合并回 LangGraph 状态。"""

        if executed_node.status == "failed":
            return {
                "node_runs": [executed_node],
                "failed": True,
                "error_message": executed_node.error_message,
            }
        if executed_node.status == "waiting_approval":
            return {
                "node_runs": [executed_node],
                "waiting_approval": True,
            }
        return {
            "context_by_node": {node_id: executed_node.output_data},
            "node_runs": [executed_node],
        }

    def _condition_router(self, node_id: str):
        """Build the LangGraph route function for one Condition node."""

        def route(state: WorkflowGraphState) -> str:
            output = state.get("context_by_node", {}).get(node_id, {})
            branch = output.get("branch")
            if branch not in {"true", "false"}:
                raise ValueError(f"条件节点 {node_id} 未产出有效的 true/false 路由结果")
            return str(branch)

        return route

    def _final_output(self, executed_nodes: list[ExecutedNode]) -> dict[str, Any]:
        """获取最终输出。"""

        for executed_node in reversed(executed_nodes):
            if executed_node.node_type == "end":
                return executed_node.output_data
        if not executed_nodes:
            return {}
        return executed_nodes[-1].output_data

    def _initial_state(
        self,
        input_data: dict[str, Any],
        resume_state: dict[str, dict[str, Any]] | None = None,
    ) -> WorkflowGraphState:
        """创建 LangGraph 初始状态。

        ``resume_state`` 预置已成功节点的输出到 ``context_by_node``，
        供审批后 DAG 续跑时把上游结果原样传给下游节点。
        """

        return {
            "workflow_input": input_data,
            "context_by_node": {**(resume_state or {})},
            "node_runs": [],
            "failed": False,
            "error_message": "",
            "waiting_approval": False,
        }

    def _to_result(self, final_state: WorkflowGraphState) -> WorkflowExecutionResult:
        """把 LangGraph 终态转换成 API 友好的结果对象。"""

        node_runs = list(final_state.get("node_runs", []))
        error_message = str(final_state.get("error_message", ""))
        if final_state.get("waiting_approval"):
            waiting_node = next(
                (node for node in reversed(node_runs) if node.status == "waiting_approval"),
                None,
            )
            return WorkflowExecutionResult(
                status="waiting_approval",
                output_data=dict(waiting_node.output_data) if waiting_node else {},
                node_runs=node_runs,
            )
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
        *,
        attempt_count: int = 1,
    ) -> ExecutedNode:
        """创建成功节点记录。"""

        return ExecutedNode(
            node_id=node_id,
            node_type=node_type,
            status="succeeded",
            input_data=node_input,
            output_data=output_data,
            elapsed_ms=int((perf_counter() - started_at) * 1000),
            attempt_count=attempt_count,
        )

    def _failed_node(
        self,
        node_id: str,
        node_type: str,
        node_input: dict[str, Any],
        exc: Exception,
        started_at: float,
        *,
        attempt_count: int = 1,
        max_attempts: int = 1,
    ) -> ExecutedNode:
        """创建失败节点记录。"""

        return ExecutedNode(
            node_id=node_id,
            node_type=node_type,
            status="failed",
            input_data=node_input,
            error_message=self._format_retry_error(
                exc,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
            ),
            elapsed_ms=int((perf_counter() - started_at) * 1000),
            attempt_count=attempt_count,
            last_error=str(exc),
        )

    def _format_retry_error(
        self,
        exc: Exception,
        *,
        attempt_count: int,
        max_attempts: int,
    ) -> str:
        """Make terminal callback failures clear in durable node traces."""

        if max_attempts <= 1:
            return str(exc)
        return (
            f"节点调用失败（已尝试 {attempt_count} 次，最多允许 {max_attempts} 次；"
            f"最后错误：{exc}）"
        )

    def _waiting_approval_node(
        self,
        node_id: str,
        node_type: str,
        node_input: dict[str, Any],
        approval: WorkflowApprovalRequired,
        started_at: float,
    ) -> ExecutedNode:
        """Persist a pause point instead of turning an approval into a failure."""

        return ExecutedNode(
            node_id=node_id,
            node_type=node_type,
            status="waiting_approval",
            input_data=node_input,
            output_data={
                "approval_id": approval.approval_id,
                "requires_approval": True,
            },
            error_message=str(approval),
            elapsed_ms=int((perf_counter() - started_at) * 1000),
        )
