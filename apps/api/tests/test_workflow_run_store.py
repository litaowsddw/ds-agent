"""WorkflowRunStore 测试。"""

from apps.api.app.domain.workflow_run import RunStatus
from apps.api.app.gateway.llm import LLMGateway, MockLLMProvider
from apps.api.app.services.agent_store import AgentStore
from apps.api.app.services.identity_store import IdentityStore
from apps.api.app.services.workflow_run_store import WorkflowRunStore
from apps.api.app.services.workflow_store import WorkflowStore

VALID_DEFINITION = {
    "version": "1.0",
    "nodes": [
        {"id": "start", "type": "start", "config": {}},
        {"id": "llm", "type": "llm", "config": {"prompt": "总结输入"}},
        {"id": "end", "type": "end", "config": {}},
    ],
    "edges": [
        {"source": "start", "target": "llm"},
        {"source": "llm", "target": "end"},
    ],
}


def test_workflow_run_executes_start_llm_end() -> None:
    """WorkflowRunStore 应能执行 Start -> LLM -> End 主链路。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)
    gateway = LLMGateway(providers={"mock": MockLLMProvider()})
    run_store = WorkflowRunStore(identity=identity, workflows=workflow_store, gateway=gateway)

    owner = identity.register_user("run-owner@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Run 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Run Agent", "")
    workflow = workflow_store.create_workflow(
        owner.user_id, agent.agent_id, "Run Workflow", "", VALID_DEFINITION
    )
    version = workflow_store.publish(owner.user_id, workflow.workflow_id)

    run = run_store.create_run(
        actor_user_id=owner.user_id,
        version_id=version.version_id,
        input_data={"text": "hello"},
        execute_immediately=True,
    )
    node_runs = run_store.list_node_runs(owner.user_id, run.run_id)

    assert run.status == RunStatus.SUCCEEDED
    assert [node_run.node_id for node_run in node_runs] == ["start", "llm", "end"]
    assert run.output_data["result"]["llm"]["text"].startswith("[mock-llm]")
    assert run.output_data["result"]["llm"]["prefix_hash"]
    assert gateway.list_logs()[0].metadata["source"] == "workflow_node"
