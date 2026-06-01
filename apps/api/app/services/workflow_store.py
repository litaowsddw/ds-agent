"""Workflow 草稿与版本管理服务。"""

from copy import deepcopy

from apps.api.app.domain.identity import new_id, utc_now
from apps.api.app.domain.workflow import Workflow, WorkflowVersion
from apps.api.app.services.agent_store import AgentStore, agent_store
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission
from apps.api.app.storage.local_state import local_state_store
from packages.workflow.dsl import WorkflowDefinition, WorkflowEdge, WorkflowNode
from packages.workflow.validator import WorkflowValidator


class WorkflowStore:
    """管理 Workflow 草稿和发布版本。"""

    def __init__(self, identity: IdentityStore, agents: AgentStore) -> None:
        # identity 用于组织权限校验。
        self.identity = identity

        # agents 用于校验 Workflow 绑定的 Agent。
        self.agents = agents

        # workflows_by_id 保存工作流元信息。
        self.workflows_by_id: dict[str, Workflow] = {}

        # versions_by_id 保存发布版本。
        self.versions_by_id: dict[str, WorkflowVersion] = {}

        # validator 是工作流 DSL 校验器。
        self.validator = WorkflowValidator()
        self._load_state()

    def create_workflow(
        self,
        actor_user_id: str,
        agent_id: str,
        name: str,
        description: str,
        draft_definition: dict[str, object],
    ) -> Workflow:
        """创建 Workflow 草稿。"""

        agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
        self.identity.assert_org_access(actor_user_id, agent.org_id, Permission.WORKFLOW_CREATE)

        workflow = Workflow(
            workflow_id=new_id("wfl"),
            org_id=agent.org_id,
            agent_id=agent.agent_id,
            name=name.strip(),
            description=description.strip(),
            draft_definition=deepcopy(draft_definition),
            created_by=actor_user_id,
        )
        self.workflows_by_id[workflow.workflow_id] = workflow
        self._save_state()
        return workflow

    def update_draft(
        self,
        actor_user_id: str,
        workflow_id: str,
        draft_definition: dict[str, object],
    ) -> Workflow:
        """更新 Workflow 草稿。"""

        workflow = self.get_workflow(actor_user_id=actor_user_id, workflow_id=workflow_id)
        self.identity.assert_org_access(actor_user_id, workflow.org_id, Permission.WORKFLOW_CREATE)
        workflow.draft_definition = deepcopy(draft_definition)
        workflow.updated_at = utc_now()
        self._save_state()
        return workflow

    def publish(self, actor_user_id: str, workflow_id: str) -> WorkflowVersion:
        """发布 Workflow 版本。"""

        workflow = self.get_workflow(actor_user_id=actor_user_id, workflow_id=workflow_id)
        self.identity.assert_org_access(actor_user_id, workflow.org_id, Permission.WORKFLOW_CREATE)

        workflow_definition = self._to_workflow_definition(workflow.draft_definition)
        validation_result = self.validator.validate(workflow_definition)
        if not validation_result["valid"]:
            raise ValueError("; ".join(validation_result["errors"]))

        version_number = self._next_version_number(workflow.workflow_id)
        version = WorkflowVersion(
            version_id=new_id("wfv"),
            workflow_id=workflow.workflow_id,
            org_id=workflow.org_id,
            version_number=version_number,
            definition=deepcopy(workflow.draft_definition),
            created_by=actor_user_id,
        )
        self.versions_by_id[version.version_id] = version
        workflow.published_version_id = version.version_id
        workflow.updated_at = utc_now()
        self._save_state()
        return version

    def get_workflow(self, actor_user_id: str, workflow_id: str) -> Workflow:
        """读取 Workflow。"""

        workflow = self.workflows_by_id.get(workflow_id)
        if workflow is None:
            raise ValueError("Workflow 不存在")

        self.identity.assert_org_access(
            actor_user_id, workflow.org_id, Permission.ORGANIZATION_READ
        )
        return workflow

    def list_workflows(
        self,
        actor_user_id: str,
        org_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[Workflow]:
        """列出用户可访问的 Workflow。"""

        workflows = list(self.workflows_by_id.values())

        if org_id is not None:
            self.identity.assert_org_access(actor_user_id, org_id, Permission.ORGANIZATION_READ)
            workflows = [workflow for workflow in workflows if workflow.org_id == org_id]
        else:
            workflows = [
                workflow
                for workflow in workflows
                if self.identity.get_membership(org_id=workflow.org_id, user_id=actor_user_id)
                is not None
            ]

        if agent_id is not None:
            agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
            workflows = [
                workflow
                for workflow in workflows
                if workflow.agent_id == agent.agent_id and workflow.org_id == agent.org_id
            ]

        return sorted(workflows, key=lambda workflow: workflow.updated_at, reverse=True)

    def get_version(self, actor_user_id: str, version_id: str) -> WorkflowVersion:
        """读取 Workflow 发布版本。"""

        version = self.versions_by_id.get(version_id)
        if version is None:
            raise ValueError("Workflow 版本不存在")

        self.identity.assert_org_access(actor_user_id, version.org_id, Permission.ORGANIZATION_READ)
        return version

    def list_versions(self, actor_user_id: str, workflow_id: str) -> list[WorkflowVersion]:
        """列出 Workflow 发布版本。"""

        workflow = self.get_workflow(actor_user_id=actor_user_id, workflow_id=workflow_id)
        versions = [
            version
            for version in self.versions_by_id.values()
            if version.workflow_id == workflow.workflow_id
        ]
        return sorted(versions, key=lambda version: version.version_number)

    def _next_version_number(self, workflow_id: str) -> int:
        """计算下一个发布版本号。"""

        version_numbers = [
            version.version_number
            for version in self.versions_by_id.values()
            if version.workflow_id == workflow_id
        ]
        return max(version_numbers, default=0) + 1

    def _load_state(self) -> None:
        """从本地状态文件恢复 Workflow 草稿和发布版本。"""

        state = local_state_store.load_bucket("workflows", {})
        if not isinstance(state, dict):
            return
        self.workflows_by_id = state.get("workflows_by_id", self.workflows_by_id)
        self.versions_by_id = state.get("versions_by_id", self.versions_by_id)

    def _save_state(self) -> None:
        """把 Workflow 草稿和发布版本保存到本地状态文件。"""

        local_state_store.save_bucket(
            "workflows",
            {
                "workflows_by_id": self.workflows_by_id,
                "versions_by_id": self.versions_by_id,
            },
        )

    def _to_workflow_definition(self, raw_definition: dict[str, object]) -> WorkflowDefinition:
        """把原始 dict 转换为 WorkflowDefinition。"""

        nodes = [
            WorkflowNode(
                node_id=str(node["id"]),
                node_type=str(node["type"]),
                config=dict(node.get("config", {})),
            )
            for node in raw_definition.get("nodes", [])
        ]
        edges = [
            WorkflowEdge(source=str(edge["source"]), target=str(edge["target"]))
            for edge in raw_definition.get("edges", [])
        ]
        return WorkflowDefinition(
            version=str(raw_definition.get("version", "1.0")), nodes=nodes, edges=edges
        )


# workflow_store 是 MVP 阶段的进程内 Workflow 存储。
workflow_store = WorkflowStore(identity=identity_store, agents=agent_store)
