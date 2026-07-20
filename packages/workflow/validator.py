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

        errors: list[str] = []

        if not workflow.nodes:
            errors.append("工作流至少需要一个 Start 节点和一个 End 节点")

        if duplicated_node_ids:
            errors.append(f"存在重复节点 ID：{duplicated_node_ids}")

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

        supported_types = {"start", "end", "llm", "rag", "tool"}
        errors: list[str] = []
        for node in workflow.nodes:
            if node.node_type not in supported_types:
                errors.append(
                    f"节点 {node.node_id}（{node.node_type}）当前仅支持画布设计，尚不能运行"
                )
                continue

            config = node.config
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
