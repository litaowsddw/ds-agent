"""Workflow Run 存储与执行协调服务。

MVP 阶段使用内存存储。这里负责创建运行记录、执行发布版本、保存节点日志。
异步执行由 Celery 任务入口复用同一个执行器逻辑。
"""

import json
from typing import Any

from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.domain.workflow_run import NodeRun, NodeRunStatus, RunStatus, WorkflowRun
from apps.api.app.gateway.llm import LLMGateway, llm_gateway
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.knowledge_store import KnowledgeStore, knowledge_store
from apps.api.app.services.mcp_store import MCPStore, mcp_store
from apps.api.app.services.rbac import Permission
from apps.api.app.services.result_cache import ResultCache, result_cache
from apps.api.app.services.workflow_store import WorkflowStore, workflow_store
from apps.api.app.storage.local_state import local_state_store
from packages.workflow.executor import WorkflowExecutionResult, WorkflowExecutor


class WorkflowRunStore:
    """管理 Workflow Run 和 Node Run。"""

    def __init__(
        self,
        identity: IdentityStore,
        workflows: WorkflowStore,
        gateway: LLMGateway | None = None,
        knowledge: KnowledgeStore | None = None,
        mcp: MCPStore | None = None,
        cache: ResultCache | None = None,
    ) -> None:
        # identity 用于运行查询和创建权限校验。
        self.identity = identity

        # workflows 用于读取发布版本和工作流元信息。
        self.workflows = workflows

        # runs_by_id 保存 Workflow Run。
        self.runs_by_id: dict[str, WorkflowRun] = {}

        # node_runs_by_run_id 保存每次运行的节点日志。
        self.node_runs_by_run_id: dict[str, list[NodeRun]] = {}

        # gateway 是 LLM 统一网关，负责 Provider 调用、错误标准化和日志。
        self.gateway = gateway or llm_gateway

        # knowledge 负责 RAG 节点检索，按组织和用户权限隔离知识库访问。
        self.knowledge = knowledge or knowledge_store

        # mcp 负责 Tool 节点授权校验，当前阶段只生成调用计划，不执行外部副作用。
        self.mcp = mcp or mcp_store

        # cache 负责 RAG、Tool 和后续 Node 输出的缓存命中统计。
        self.cache = cache or result_cache

        # executor_factory 会在每次运行时注入组织与用户上下文，确保模型供应商配置按组织隔离。
        self.executor_factory = WorkflowExecutor
        self._load_state()

    def create_run(
        self,
        actor_user_id: str,
        version_id: str,
        input_data: dict[str, Any],
        execute_immediately: bool = True,
    ) -> WorkflowRun:
        """创建 Workflow Run。"""

        version = self.workflows.get_version(actor_user_id=actor_user_id, version_id=version_id)
        workflow = self.workflows.get_workflow(
            actor_user_id=actor_user_id,
            workflow_id=version.workflow_id,
        )
        self.identity.assert_org_access(actor_user_id, version.org_id, Permission.WORKFLOW_CREATE)

        run = WorkflowRun(
            run_id=new_id("run"),
            org_id=version.org_id,
            workflow_id=version.workflow_id,
            version_id=version.version_id,
            agent_id=workflow.agent_id,
            input_data=input_data,
            created_by=actor_user_id,
        )
        self.runs_by_id[run.run_id] = run
        self.node_runs_by_run_id[run.run_id] = []
        self._save_state()

        if execute_immediately:
            self.execute_run(actor_user_id=actor_user_id, run_id=run.run_id)

        return run

    def execute_run(self, actor_user_id: str, run_id: str) -> WorkflowRun:
        """同步执行 Workflow Run。"""

        run = self.get_run(actor_user_id=actor_user_id, run_id=run_id)
        version = self.workflows.get_version(actor_user_id=actor_user_id, version_id=run.version_id)

        run.status = RunStatus.RUNNING
        run.updated_at = utc_now()

        executor = self.executor_factory(
            llm_gateway=lambda config, node_input: self.gateway.generate_from_workflow_node(
                {
                    **config,
                    "_org_id": run.org_id,
                    "_actor_user_id": actor_user_id,
                },
                node_input,
            ),
            rag_search=lambda config, node_input: self._execute_rag_node(
                config=config,
                node_input=node_input,
                actor_user_id=actor_user_id,
                org_id=run.org_id,
            ),
            tool_call=lambda config, node_input: self._execute_tool_node(
                config=config,
                node_input=node_input,
                actor_user_id=actor_user_id,
                agent_id=run.agent_id,
                org_id=run.org_id,
            ),
        )
        result = executor.execute(definition=version.definition, input_data=run.input_data)
        self._apply_execution_result(run=run, result=result)
        return run

    def _execute_rag_node(
        self,
        config: dict[str, Any],
        node_input: dict[str, Any],
        actor_user_id: str,
        org_id: str,
    ) -> dict[str, Any]:
        """执行 RAG 节点：生成 query、校验知识库权限、检索 Chunk 并写入缓存。"""

        kb_id = str(config.get("kb_id") or "").strip()
        if not kb_id:
            raise ValueError("RAG 节点缺少 kb_id")

        limit = self._positive_int(config.get("limit"), default=5, maximum=20)
        query = self._render_query_template(
            template=str(config.get("query_template") or ""),
            node_input=node_input,
        )
        cache_key_data = {
            "org_id": org_id,
            "kb_id": kb_id,
            "query": query,
            "limit": limit,
        }

        cached = self.cache.get("rag", cache_key_data)
        if cached is not None:
            return self._with_cache_state(
                value=dict(cached.value),
                cache_hit=True,
                cache_key=cached.cache_key,
            )

        chunks = self.knowledge.search(
            actor_user_id=actor_user_id,
            kb_id=kb_id,
            query=query,
            limit=limit,
        )
        output = {
            "kb_id": kb_id,
            "query": query,
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "content": chunk.content,
                    "sequence": chunk.sequence,
                    "estimated_tokens": chunk.estimated_tokens,
                    "embedding_model": chunk.embedding_model,
                    "vector_indexed": chunk.vector_indexed,
                    "similarity_score": chunk.similarity_score,
                }
                for chunk in chunks
            ],
            "total_estimated_tokens": sum(chunk.estimated_tokens for chunk in chunks),
            "upstream": node_input.get("upstream", {}),
        }
        entry = self.cache.put("rag", cache_key_data, output)
        return self._with_cache_state(value=output, cache_hit=False, cache_key=entry.cache_key)

    def _execute_tool_node(
        self,
        config: dict[str, Any],
        node_input: dict[str, Any],
        actor_user_id: str,
        agent_id: str,
        org_id: str,
    ) -> dict[str, Any]:
        """执行 Tool 节点：校验 MCP 授权，生成安全的工具调用计划并写入缓存。"""

        tool_id = str(config.get("tool_id") or "").strip()
        if not tool_id:
            raise ValueError("Tool 节点缺少 tool_id")

        arguments = config.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("Tool 节点 arguments 必须是 JSON 对象")

        cache_key_data = {
            "org_id": org_id,
            "agent_id": agent_id,
            "tool_id": tool_id,
            "arguments": arguments,
        }
        cached = self.cache.get("tool", cache_key_data)
        if cached is not None:
            return self._with_cache_state(
                value=dict(cached.value),
                cache_hit=True,
                cache_key=cached.cache_key,
            )

        tool = self.mcp.assert_agent_can_call_tool(
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            tool_id=tool_id,
        )
        risk_level = str(config.get("risk_level") or tool.risk_level or "low")
        requires_approval = risk_level.lower() in {"high", "critical"}
        output = {
            "tool_id": tool.tool_id,
            "server_id": tool.server_id,
            "tool_name": tool.name,
            "description": tool.description,
            "risk_level": risk_level,
            "arguments": arguments,
            "upstream": node_input.get("upstream", {}),
            "requires_approval": requires_approval,
            "status": "requires_approval" if requires_approval else "planned",
            "message": "MVP 阶段已完成授权校验并生成调用计划，未触发外部 MCP 副作用。",
        }
        entry = self.cache.put("tool", cache_key_data, output)
        return self._with_cache_state(value=output, cache_hit=False, cache_key=entry.cache_key)

    def _render_query_template(self, template: str, node_input: dict[str, Any]) -> str:
        """渲染 RAG 查询模板；未配置时从 workflow_input 自动提取查询文本。"""

        workflow_input = node_input.get("workflow_input", {})
        upstream = node_input.get("upstream", {})
        if isinstance(workflow_input, dict):
            input_text = str(workflow_input.get("text") or workflow_input.get("query") or "")
        else:
            input_text = str(workflow_input)

        if not template.strip():
            return input_text or self._stable_json(workflow_input)

        return (
            template.replace("{{input.text}}", input_text)
            .replace("{{input.query}}", input_text)
            .replace("{{workflow_input}}", self._stable_json(workflow_input))
            .replace("{{upstream}}", self._stable_json(upstream))
            .strip()
        )

    def _positive_int(self, value: Any, default: int, maximum: int) -> int:
        """把节点配置里的数值参数收敛到可控范围。"""

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, maximum))

    def _stable_json(self, value: Any) -> str:
        """生成稳定 JSON 文本，用于模板替换和缓存 key 组成。"""

        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    def _with_cache_state(
        self,
        value: dict[str, Any],
        cache_hit: bool,
        cache_key: str,
    ) -> dict[str, Any]:
        """把缓存命中状态附加到节点输出，避免污染缓存中的原始业务结果。"""

        return {**value, "cache_hit": cache_hit, "cache_key": cache_key}

    def attach_celery_task(
        self, actor_user_id: str, run_id: str, celery_task_id: str
    ) -> WorkflowRun:
        """把 Celery task id 记录到 Workflow Run。"""

        run = self.get_run(actor_user_id=actor_user_id, run_id=run_id)
        run.celery_task_id = celery_task_id
        run.updated_at = utc_now()
        self._save_state()
        return run

    def get_run(self, actor_user_id: str, run_id: str) -> WorkflowRun:
        """读取 Workflow Run。"""

        run = self.runs_by_id.get(run_id)
        if run is None:
            raise ValueError("Workflow Run 不存在")

        self.identity.assert_org_access(actor_user_id, run.org_id, Permission.ORGANIZATION_READ)
        return run

    def list_runs(
        self,
        actor_user_id: str,
        org_id: str | None = None,
        workflow_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[WorkflowRun]:
        """列出用户可访问的 Workflow Run。"""

        runs = list(self.runs_by_id.values())

        if org_id is not None:
            self.identity.assert_org_access(actor_user_id, org_id, Permission.ORGANIZATION_READ)
            runs = [run for run in runs if run.org_id == org_id]
        else:
            runs = [
                run
                for run in runs
                if self.identity.get_membership(org_id=run.org_id, user_id=actor_user_id)
                is not None
            ]

        if workflow_id is not None:
            runs = [run for run in runs if run.workflow_id == workflow_id]

        if agent_id is not None:
            runs = [run for run in runs if run.agent_id == agent_id]

        return sorted(runs, key=lambda run: run.updated_at, reverse=True)

    def list_node_runs(self, actor_user_id: str, run_id: str) -> list[NodeRun]:
        """列出 Workflow Run 的节点日志。"""

        run = self.get_run(actor_user_id=actor_user_id, run_id=run_id)
        return list(self.node_runs_by_run_id[run.run_id])

    def _apply_execution_result(self, run: WorkflowRun, result: WorkflowExecutionResult) -> None:
        """把执行器结果写入运行记录。"""

        run.status = RunStatus(result.status)
        run.output_data = result.output_data
        run.error_message = result.error_message
        run.updated_at = utc_now()

        node_runs: list[NodeRun] = []
        for index, executed_node in enumerate(result.node_runs, start=1):
            node_runs.append(
                NodeRun(
                    node_run_id=new_id("ndr"),
                    run_id=run.run_id,
                    node_id=executed_node.node_id,
                    node_type=executed_node.node_type,
                    status=NodeRunStatus(executed_node.status),
                    input_data=executed_node.input_data,
                    output_data=executed_node.output_data,
                    error_message=executed_node.error_message,
                    elapsed_ms=executed_node.elapsed_ms,
                    sequence=index,
                )
            )
        self.node_runs_by_run_id[run.run_id] = node_runs
        self._save_state()

    def _load_state(self) -> None:
        """从本地状态文件恢复 Workflow Run 与 Node Run。"""

        state = local_state_store.load_bucket("workflow_runs", {})
        if not isinstance(state, dict):
            return
        self.runs_by_id = state.get("runs_by_id", self.runs_by_id)
        self.node_runs_by_run_id = state.get(
            "node_runs_by_run_id",
            self.node_runs_by_run_id,
        )

    def _save_state(self) -> None:
        """把 Workflow Run 与 Node Run 保存到本地状态文件。"""

        local_state_store.save_bucket(
            "workflow_runs",
            {
                "runs_by_id": self.runs_by_id,
                "node_runs_by_run_id": self.node_runs_by_run_id,
            },
        )


# workflow_run_store 是 MVP 阶段的进程内运行存储。
workflow_run_store = WorkflowRunStore(identity=identity_store, workflows=workflow_store)
