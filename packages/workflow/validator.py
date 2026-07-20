"""Workflow DAG 校验器。"""

from packages.workflow.dsl import WorkflowDefinition
from packages.workflow.budget import WorkflowBudgetConfigurationError, execution_limits_from_definition
from packages.workflow.conditions import WorkflowConditionError, parse_condition_config
from packages.workflow.reliability import (
    WorkflowReliabilityConfigurationError,
    reliability_policy_for_node,
)
from packages.workflow.templates import (
    WorkflowTemplateError,
    collect_template_references,
    is_special_root,
)

_RESERVED_TEMPLATE_NAMESPACES = {"input", "workflow_input", "upstream"}


class WorkflowValidator:
    """校验工作流结构是否合法。"""

    def validate(self, workflow: WorkflowDefinition) -> dict[str, object]:
        """校验工作流定义。

        MVP 阶段先校验节点 ID 唯一和 start/end 节点存在，后续增加环检测和 schema 校验。
        """

        # node_ids 保存所有节点 ID，用于检查重复和连线引用。
        node_ids = [node.node_id for node in workflow.nodes]

        # duplicated_node_ids 保存重复节点，非空时工作流不可发布。
        duplicated_node_ids = sorted(
            {node_id for node_id in node_ids if node_ids.count(node_id) > 1}
        )

        errors: list[str] = []

        if not workflow.nodes:
            errors.append("工作流至少需要一个 Start 节点和一个 End 节点")

        if duplicated_node_ids:
            errors.append(f"存在重复节点 ID：{duplicated_node_ids}")

        reserved_node_ids = sorted(set(node_ids) & _RESERVED_TEMPLATE_NAMESPACES)
        if reserved_node_ids:
            errors.append(f"节点 ID 不能使用保留模板命名空间：{reserved_node_ids}")

        start_nodes = [node for node in workflow.nodes if node.node_type == "start"]
        end_nodes = [node for node in workflow.nodes if node.node_type == "end"]

        if not start_nodes:
            errors.append("工作流必须包含 start 节点")
        elif len(start_nodes) > 1:
            errors.append("工作流只能包含一个 start 节点")

        if not end_nodes:
            errors.append("工作流必须包含 end 节点")
        elif len(end_nodes) > 1:
            errors.append("工作流只能包含一个 end 节点")

        edge_errors = self._validate_edges(workflow=workflow, node_ids=set(node_ids))
        errors.extend(edge_errors)

        errors.extend(self._validate_condition_nodes(workflow))

        if not edge_errors and self._has_cycle(workflow=workflow):
            errors.append("工作流不能包含环")

        if not edge_errors and len(start_nodes) == 1 and len(end_nodes) == 1:
            errors.extend(
                self._validate_execution_path(
                    workflow=workflow,
                    start_node_id=start_nodes[0].node_id,
                    end_node_id=end_nodes[0].node_id,
                )
            )

        errors.extend(self._validate_executable_nodes(workflow))
        errors.extend(self._validate_template_references(workflow))
        try:
            execution_limits_from_definition({"execution_limits": workflow.execution_limits})
        except WorkflowBudgetConfigurationError as exc:
            errors.append(str(exc))

        return {"valid": not errors, "errors": errors}

    def _validate_edges(self, workflow: WorkflowDefinition, node_ids: set[str]) -> list[str]:
        """校验连线是否引用存在的节点。"""

        errors: list[str] = []
        node_types = {node.node_id: node.node_type for node in workflow.nodes}
        for edge in workflow.edges:
            if edge.source not in node_ids:
                errors.append(f"连线起点不存在：{edge.source}")
            if edge.target not in node_ids:
                errors.append(f"连线终点不存在：{edge.target}")
            source_type = node_types.get(edge.source)
            if source_type == "condition":
                if edge.branch not in {"true", "false"}:
                    errors.append(
                        f"条件节点 {edge.source} 的出边必须声明 branch 为 true 或 false"
                    )
            elif edge.branch is not None:
                errors.append(
                    f"普通节点 {edge.source} 的连线不能声明 branch；只有 Condition 可使用 true/false 出边"
                )
        return errors

    def _validate_condition_nodes(self, workflow: WorkflowDefinition) -> list[str]:
        """Validate the limited condition DSL and its two explicit routes."""

        errors: list[str] = []
        edges_by_source: dict[str, list[object]] = {}
        for edge in workflow.edges:
            edges_by_source.setdefault(edge.source, []).append(edge)

        for node in workflow.nodes:
            if node.node_type != "condition":
                continue
            try:
                parse_condition_config(node.config)
            except WorkflowConditionError as exc:
                errors.append(f"条件节点 {node.node_id} 配置无效：{exc}")

            branch_edges = edges_by_source.get(node.node_id, [])
            true_edges = [edge for edge in branch_edges if getattr(edge, "branch", None) == "true"]
            false_edges = [edge for edge in branch_edges if getattr(edge, "branch", None) == "false"]
            if len(true_edges) != 1:
                errors.append(f"条件节点 {node.node_id} 必须且只能有一条 true 出边")
            if len(false_edges) != 1:
                errors.append(f"条件节点 {node.node_id} 必须且只能有一条 false 出边")
        return errors

    def _has_cycle(self, workflow: WorkflowDefinition) -> bool:
        """检测工作流是否包含环。"""

        # adjacency 是邻接表，用于深度优先遍历。
        adjacency: dict[str, list[str]] = {node.node_id: [] for node in workflow.nodes}
        for edge in workflow.edges:
            adjacency[edge.source].append(edge.target)

        # visiting 保存当前递归栈中的节点。
        visiting: set[str] = set()

        # visited 保存已经确认无环的节点。
        visited: set[str] = set()

        def visit(node_id: str) -> bool:
            """返回从当前节点出发是否遇到环。"""

            if node_id in visiting:
                return True
            if node_id in visited:
                return False

            visiting.add(node_id)
            for next_node_id in adjacency.get(node_id, []):
                if visit(next_node_id):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(visit(node.node_id) for node in workflow.nodes)

    def _validate_execution_path(
        self,
        workflow: WorkflowDefinition,
        start_node_id: str,
        end_node_id: str,
    ) -> list[str]:
        """确保画布上的每个步骤都会落在一条可执行的 Start -> End 路径中。"""

        adjacency: dict[str, list[str]] = {node.node_id: [] for node in workflow.nodes}
        reverse_adjacency: dict[str, list[str]] = {node.node_id: [] for node in workflow.nodes}
        incoming: dict[str, int] = {node.node_id: 0 for node in workflow.nodes}
        outgoing: dict[str, int] = {node.node_id: 0 for node in workflow.nodes}
        for edge in workflow.edges:
            adjacency[edge.source].append(edge.target)
            reverse_adjacency[edge.target].append(edge.source)
            incoming[edge.target] += 1
            outgoing[edge.source] += 1

        errors: list[str] = []
        if incoming[start_node_id] > 0:
            errors.append("Start 节点不能有输入连线")
        if outgoing[end_node_id] > 0:
            errors.append("End 节点不能有输出连线")

        reachable_from_start = self._reachable_nodes(start_node_id, adjacency)
        can_reach_end = self._reachable_nodes(end_node_id, reverse_adjacency)
        if end_node_id not in reachable_from_start:
            errors.append("End 节点无法从 Start 节点到达")

        for node in workflow.nodes:
            if node.node_id not in reachable_from_start:
                errors.append(f"节点 {node.node_id} 未连接到 Start 节点")
            elif node.node_id not in can_reach_end:
                errors.append(f"节点 {node.node_id} 无法到达 End 节点")
        return errors

    def _reachable_nodes(self, root: str, adjacency: dict[str, list[str]]) -> set[str]:
        """返回从 root 沿给定邻接表可以到达的节点。"""

        visited: set[str] = set()
        pending = [root]
        while pending:
            node_id = pending.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            pending.extend(adjacency.get(node_id, []))
        return visited

    def _validate_executable_nodes(self, workflow: WorkflowDefinition) -> list[str]:
        """在发布前拦住当前执行器尚不支持或配置不完整的步骤。"""

        supported_types = {"start", "end", "llm", "rag", "tool", "condition"}
        errors: list[str] = []
        for node in workflow.nodes:
            if node.node_type not in supported_types:
                errors.append(
                    f"节点 {node.node_id}（{node.node_type}）当前仅支持画布设计，尚不能运行"
                )
                continue

            config = node.config
            try:
                reliability_policy_for_node(node.node_type, config)
            except WorkflowReliabilityConfigurationError as exc:
                errors.append(f"节点 {node.node_id} 的 reliability 配置无效：{exc}")
            if node.node_type == "llm":
                if not str(config.get("provider") or "").strip():
                    errors.append(f"LLM 节点 {node.node_id} 未选择模型提供商")
                if not str(config.get("model") or "").strip():
                    errors.append(f"LLM 节点 {node.node_id} 未选择模型")
            elif node.node_type == "rag" and not str(config.get("kb_id") or "").strip():
                errors.append(f"知识检索节点 {node.node_id} 未选择知识库")
            elif node.node_type == "tool":
                if not str(config.get("tool_id") or "").strip():
                    errors.append(f"工具节点 {node.node_id} 未选择已授权工具")
                arguments = config.get("arguments", {})
                if not isinstance(arguments, dict):
                    errors.append(f"工具节点 {node.node_id} 的参数必须是 JSON 对象")
        return errors

    def _validate_template_references(self, workflow: WorkflowDefinition) -> list[str]:
        """Reject malformed, missing, and non-upstream template references.

        Field existence cannot always be known before a run (LLM and Tool
        outputs are dynamic), so field-level verification remains strict at
        execution time.  Publishing still catches the expensive authoring
        mistakes: invalid syntax, unknown node IDs, self references, and
        references to a node outside the current node's upstream lineage.
        """

        node_ids = {node.node_id for node in workflow.nodes}
        reverse_adjacency: dict[str, list[str]] = {node.node_id: [] for node in workflow.nodes}
        for edge in workflow.edges:
            if edge.source in node_ids and edge.target in node_ids:
                reverse_adjacency[edge.target].append(edge.source)

        errors: list[str] = []
        for node in workflow.nodes:
            upstream_node_ids = self._reachable_nodes(node.node_id, reverse_adjacency)
            upstream_node_ids.discard(node.node_id)
            for location, template in self._template_strings(node.config, "config"):
                try:
                    references = collect_template_references(template)
                except WorkflowTemplateError as exc:
                    errors.append(f"节点 {node.node_id} 的 {location}：{exc}")
                    continue
                for reference in references:
                    if is_special_root(reference.root):
                        continue
                    if reference.root not in node_ids:
                        errors.append(
                            f"节点 {node.node_id} 的 {location} 引用了不存在的节点输出："
                            f"{{{{{reference.expression}}}}}"
                        )
                    elif reference.root not in upstream_node_ids:
                        errors.append(
                            f"节点 {node.node_id} 的 {location} 只能引用已连接上游节点的输出："
                            f"{{{{{reference.expression}}}}}"
                        )
        return errors

    def _template_strings(self, value: object, location: str):
        """Yield strings from a config object with a stable human-readable path."""

        if isinstance(value, str):
            yield location, value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield from self._template_strings(item, f"{location}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from self._template_strings(item, f"{location}[{index}]")
