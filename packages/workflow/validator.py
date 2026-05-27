"""Workflow DAG 校验器。"""

from packages.workflow.dsl import WorkflowDefinition


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

        # node_types 保存所有节点类型，用于检查必要节点。
        node_types = [node.node_type for node in workflow.nodes]

        errors: list[str] = []

        if duplicated_node_ids:
            errors.append(f"存在重复节点 ID：{duplicated_node_ids}")

        if "start" not in node_types:
            errors.append("工作流必须包含 start 节点")

        if "end" not in node_types:
            errors.append("工作流必须包含 end 节点")

        edge_errors = self._validate_edges(workflow=workflow, node_ids=set(node_ids))
        errors.extend(edge_errors)

        if not edge_errors and self._has_cycle(workflow=workflow):
            errors.append("工作流不能包含环")

        return {"valid": not errors, "errors": errors}

    def _validate_edges(self, workflow: WorkflowDefinition, node_ids: set[str]) -> list[str]:
        """校验连线是否引用存在的节点。"""

        errors: list[str] = []
        for edge in workflow.edges:
            if edge.source not in node_ids:
                errors.append(f"连线起点不存在：{edge.source}")
            if edge.target not in node_ids:
                errors.append(f"连线终点不存在：{edge.target}")
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
