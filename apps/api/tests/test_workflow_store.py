"""WorkflowStore 测试。"""

import pytest

from apps.api.app.services.agent_store import AgentStore
from apps.api.app.services.identity_store import IdentityStore
from apps.api.app.services.workflow_store import WorkflowStore


VALID_DEFINITION = {
    "version": "1.0",
    "nodes": [
        {"id": "start", "type": "start", "config": {}},
        {"id": "llm", "type": "llm", "config": {"prompt": "hello"}},
        {"id": "end", "type": "end", "config": {}},
    ],
    "edges": [
        {"source": "start", "target": "llm"},
        {"source": "llm", "target": "end"},
    ],
}


def test_workflow_can_be_published_as_immutable_version() -> None:
    """合法 Workflow 可以发布为不可变版本。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)

    owner = identity.register_user("workflow-owner@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Workflow 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Workflow Agent", "")
    workflow = workflow_store.create_workflow(owner.user_id, agent.agent_id, "摘要流", "", VALID_DEFINITION)

    version = workflow_store.publish(owner.user_id, workflow.workflow_id)
    workflow_store.update_draft(
        owner.user_id,
        workflow.workflow_id,
        {**VALID_DEFINITION, "nodes": [*VALID_DEFINITION["nodes"], {"id": "extra", "type": "end"}]},
    )

    stored_version = workflow_store.get_version(owner.user_id, version.version_id)

    assert stored_version.definition == VALID_DEFINITION
    assert stored_version.version_number == 1


def test_workflow_publish_rejects_cycle() -> None:
    """包含环的 Workflow 不允许发布。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)

    owner = identity.register_user("workflow-cycle@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Workflow Cycle 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Cycle Agent", "")
    cyclic_definition = {
        "version": "1.0",
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "end"},
            {"source": "end", "target": "start"},
        ],
    }
    workflow = workflow_store.create_workflow(owner.user_id, agent.agent_id, "环形流", "", cyclic_definition)

    with pytest.raises(ValueError):
        workflow_store.publish(owner.user_id, workflow.workflow_id)

