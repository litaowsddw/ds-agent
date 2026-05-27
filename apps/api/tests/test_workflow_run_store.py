"""WorkflowRunStore 测试。"""

from apps.api.app.domain.workflow_run import RunStatus
from apps.api.app.domain.mcp import MCPTransport
from apps.api.app.gateway.llm import LLMGateway, MockLLMProvider
from apps.api.app.services.agent_store import AgentStore
from apps.api.app.services.identity_store import IdentityStore
from apps.api.app.services.knowledge_store import KnowledgeStore
from apps.api.app.services.mcp_store import MCPStore
from apps.api.app.services.result_cache import ResultCache
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


def test_workflow_run_executes_rag_llm_tool_with_cache() -> None:
    """WorkflowRunStore 应执行 Start -> RAG -> LLM -> Tool -> End 并复用 RAG/Tool 缓存。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)
    knowledge = KnowledgeStore(identity=identity)
    mcp = MCPStore(identity=identity, agents=agent_store)
    cache = ResultCache(max_size=20)
    gateway = LLMGateway(providers={"mock": MockLLMProvider()})
    run_store = WorkflowRunStore(
        identity=identity,
        workflows=workflow_store,
        gateway=gateway,
        knowledge=knowledge,
        mcp=mcp,
        cache=cache,
    )

    owner = identity.register_user("rag-tool-owner@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "RAG Tool 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "RAG Tool Agent", "")
    kb = knowledge.create_knowledge_base(owner.user_id, organization.org_id, "政策库", "")
    knowledge.upload_document(
        actor_user_id=owner.user_id,
        kb_id=kb.kb_id,
        title="退款政策",
        content="退款 政策 要求 7 天内可处理，并需要保留订单号。",
        chunk_size=200,
    )
    server = mcp.register_server(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        name="客服 MCP",
        transport=MCPTransport.HTTP,
        url="http://localhost:18080/mcp",
    )
    tool = mcp.upsert_tool_snapshot(
        actor_user_id=owner.user_id,
        server_id=server.server_id,
        name="create_ticket",
        description="创建客服工单",
        input_schema={"type": "object"},
        risk_level="low",
    )
    mcp.set_agent_mcp_policy(
        actor_user_id=owner.user_id,
        agent_id=agent.agent_id,
        server_id=server.server_id,
        allowed=True,
    )

    definition = {
        "version": "1.0",
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {
                "id": "rag",
                "type": "rag",
                "config": {"kb_id": kb.kb_id, "query_template": "{{input.text}}", "limit": 3},
            },
            {"id": "llm", "type": "llm", "config": {"prompt": "结合检索结果回答"}},
            {
                "id": "tool",
                "type": "tool",
                "config": {
                    "tool_id": tool.tool_id,
                    "arguments": {"action": "create_ticket"},
                    "risk_level": "low",
                },
            },
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "start", "target": "rag"},
            {"source": "rag", "target": "llm"},
            {"source": "llm", "target": "tool"},
            {"source": "tool", "target": "end"},
        ],
    }
    workflow = workflow_store.create_workflow(
        owner.user_id, agent.agent_id, "RAG Tool Workflow", "", definition
    )
    version = workflow_store.publish(owner.user_id, workflow.workflow_id)

    first_run = run_store.create_run(
        actor_user_id=owner.user_id,
        version_id=version.version_id,
        input_data={"text": "退款 政策"},
        execute_immediately=True,
    )
    first_nodes = run_store.list_node_runs(owner.user_id, first_run.run_id)
    rag_output = first_nodes[1].output_data
    tool_output = first_nodes[3].output_data

    assert first_run.status == RunStatus.SUCCEEDED
    assert [node_run.node_id for node_run in first_nodes] == ["start", "rag", "llm", "tool", "end"]
    assert rag_output["query"] == "退款 政策"
    assert rag_output["chunks"][0]["content"].startswith("退款 政策")
    assert rag_output["cache_hit"] is False
    assert tool_output["status"] == "planned"
    assert tool_output["requires_approval"] is False
    assert tool_output["cache_hit"] is False

    second_run = run_store.create_run(
        actor_user_id=owner.user_id,
        version_id=version.version_id,
        input_data={"text": "退款 政策"},
        execute_immediately=True,
    )
    second_nodes = run_store.list_node_runs(owner.user_id, second_run.run_id)

    assert second_run.status == RunStatus.SUCCEEDED
    assert second_nodes[1].output_data["cache_hit"] is True
    assert second_nodes[3].output_data["cache_hit"] is True
    assert cache.stats()["total_hits"] >= 2


def test_workflow_run_rag_no_hit_still_succeeds() -> None:
    """RAG 节点无命中时应返回空 chunks，但工作流仍可成功。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)
    knowledge = KnowledgeStore(identity=identity)
    run_store = WorkflowRunStore(
        identity=identity,
        workflows=workflow_store,
        gateway=LLMGateway(providers={"mock": MockLLMProvider()}),
        knowledge=knowledge,
        mcp=MCPStore(identity=identity, agents=agent_store),
        cache=ResultCache(max_size=20),
    )

    owner = identity.register_user("rag-empty@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "RAG Empty 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "RAG Agent", "")
    kb = knowledge.create_knowledge_base(owner.user_id, organization.org_id, "空命中库", "")
    knowledge.upload_document(owner.user_id, kb.kb_id, "产品说明", "只包含安装流程", chunk_size=200)

    workflow = workflow_store.create_workflow(
        owner.user_id,
        agent.agent_id,
        "RAG Empty Workflow",
        "",
        {
            "version": "1.0",
            "nodes": [
                {"id": "start", "type": "start", "config": {}},
                {"id": "rag", "type": "rag", "config": {"kb_id": kb.kb_id, "query_template": "退款", "limit": 2}},
                {"id": "end", "type": "end", "config": {}},
            ],
            "edges": [{"source": "start", "target": "rag"}, {"source": "rag", "target": "end"}],
        },
    )
    version = workflow_store.publish(owner.user_id, workflow.workflow_id)
    run = run_store.create_run(owner.user_id, version.version_id, {"text": "退款"}, True)
    node_runs = run_store.list_node_runs(owner.user_id, run.run_id)

    assert run.status == RunStatus.SUCCEEDED
    assert node_runs[1].output_data["chunks"] == []


def test_workflow_run_fails_when_rag_kb_is_cross_org() -> None:
    """RAG 节点引用其他组织知识库时应失败，避免跨租户数据泄露。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)
    knowledge = KnowledgeStore(identity=identity)
    run_store = WorkflowRunStore(
        identity=identity,
        workflows=workflow_store,
        gateway=LLMGateway(providers={"mock": MockLLMProvider()}),
        knowledge=knowledge,
        mcp=MCPStore(identity=identity, agents=agent_store),
        cache=ResultCache(max_size=20),
    )

    owner = identity.register_user("rag-cross-owner@example.com", "Owner", "password123")
    other_owner = identity.register_user("rag-cross-other@example.com", "Other", "password123")
    organization = identity.create_organization(owner.user_id, "RAG Owner 组织")
    other_organization = identity.create_organization(other_owner.user_id, "RAG Other 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "RAG Agent", "")
    other_kb = knowledge.create_knowledge_base(other_owner.user_id, other_organization.org_id, "其他组织知识库", "")
    knowledge.upload_document(other_owner.user_id, other_kb.kb_id, "私有文档", "跨组织私有内容", chunk_size=200)

    workflow = workflow_store.create_workflow(
        owner.user_id,
        agent.agent_id,
        "Cross Org RAG Workflow",
        "",
        {
            "version": "1.0",
            "nodes": [
                {"id": "start", "type": "start", "config": {}},
                {"id": "rag", "type": "rag", "config": {"kb_id": other_kb.kb_id, "query_template": "私有"}},
                {"id": "end", "type": "end", "config": {}},
            ],
            "edges": [{"source": "start", "target": "rag"}, {"source": "rag", "target": "end"}],
        },
    )
    version = workflow_store.publish(owner.user_id, workflow.workflow_id)
    run = run_store.create_run(owner.user_id, version.version_id, {"text": "私有"}, True)
    node_runs = run_store.list_node_runs(owner.user_id, run.run_id)

    assert run.status == RunStatus.FAILED
    assert node_runs[-1].node_id == "rag"
    assert node_runs[-1].status.value == "failed"


def test_workflow_run_fails_when_tool_is_not_authorized() -> None:
    """Tool 节点调用未授权 MCP Tool 时应失败并记录节点错误。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)
    mcp = MCPStore(identity=identity, agents=agent_store)
    run_store = WorkflowRunStore(
        identity=identity,
        workflows=workflow_store,
        gateway=LLMGateway(providers={"mock": MockLLMProvider()}),
        knowledge=KnowledgeStore(identity=identity),
        mcp=mcp,
        cache=ResultCache(max_size=20),
    )

    owner = identity.register_user("tool-denied@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Tool Denied 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Tool Agent", "")
    server = mcp.register_server(owner.user_id, organization.org_id, "危险 MCP", MCPTransport.HTTP, "http://localhost")
    tool = mcp.upsert_tool_snapshot(
        owner.user_id,
        server.server_id,
        "delete_record",
        "删除记录",
        {"type": "object"},
        risk_level="high",
    )

    workflow = workflow_store.create_workflow(
        owner.user_id,
        agent.agent_id,
        "Unauthorized Tool Workflow",
        "",
        {
            "version": "1.0",
            "nodes": [
                {"id": "start", "type": "start", "config": {}},
                {"id": "tool", "type": "tool", "config": {"tool_id": tool.tool_id, "arguments": {}}},
                {"id": "end", "type": "end", "config": {}},
            ],
            "edges": [{"source": "start", "target": "tool"}, {"source": "tool", "target": "end"}],
        },
    )
    version = workflow_store.publish(owner.user_id, workflow.workflow_id)
    run = run_store.create_run(owner.user_id, version.version_id, {"text": "删除"}, True)
    node_runs = run_store.list_node_runs(owner.user_id, run.run_id)

    assert run.status == RunStatus.FAILED
    assert node_runs[-1].node_id == "tool"
    assert node_runs[-1].status.value == "failed"
    assert "MCP Tool" in node_runs[-1].error_message


def test_workflow_run_high_risk_tool_requires_approval() -> None:
    """高风险 Tool 已授权时应生成 requires_approval 调用计划，不执行外部副作用。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)
    mcp = MCPStore(identity=identity, agents=agent_store)
    run_store = WorkflowRunStore(
        identity=identity,
        workflows=workflow_store,
        gateway=LLMGateway(providers={"mock": MockLLMProvider()}),
        knowledge=KnowledgeStore(identity=identity),
        mcp=mcp,
        cache=ResultCache(max_size=20),
    )

    owner = identity.register_user("tool-high-risk@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Tool Approval 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Approval Agent", "")
    server = mcp.register_server(owner.user_id, organization.org_id, "审批 MCP", MCPTransport.HTTP, "http://localhost")
    tool = mcp.upsert_tool_snapshot(
        owner.user_id,
        server.server_id,
        "refund_payment",
        "执行退款",
        {"type": "object"},
        risk_level="high",
    )
    mcp.set_agent_mcp_policy(owner.user_id, agent.agent_id, server.server_id, True)

    workflow = workflow_store.create_workflow(
        owner.user_id,
        agent.agent_id,
        "High Risk Tool Workflow",
        "",
        {
            "version": "1.0",
            "nodes": [
                {"id": "start", "type": "start", "config": {}},
                {
                    "id": "tool",
                    "type": "tool",
                    "config": {"tool_id": tool.tool_id, "arguments": {"order_id": "A100"}, "risk_level": "high"},
                },
                {"id": "end", "type": "end", "config": {}},
            ],
            "edges": [{"source": "start", "target": "tool"}, {"source": "tool", "target": "end"}],
        },
    )
    version = workflow_store.publish(owner.user_id, workflow.workflow_id)
    run = run_store.create_run(owner.user_id, version.version_id, {"text": "退款"}, True)
    node_runs = run_store.list_node_runs(owner.user_id, run.run_id)

    assert run.status == RunStatus.SUCCEEDED
    assert node_runs[1].output_data["requires_approval"] is True
    assert node_runs[1].output_data["status"] == "requires_approval"
