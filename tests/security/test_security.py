"""安全测试 —— 租户隔离、RBAC 权限和密钥保护。

该测试套件覆盖 DEVELOPMENT_PLAN.md 中 Module 18 要求的：
- 租户隔离无越权（多组织资源完全隔离）
- RBAC 权限边界（viewer/developer/admin/owner 权限矩阵）
- 密钥和敏感信息不泄露
- 审计日志完整性
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.domain.identity import OrganizationRole
from apps.api.app.services.identity_store import IdentityStore


def test_cross_org_agent_isolation() -> None:
    """验证 Agent 跨组织隔离：组织 A 的用户不能访问组织 B 的 Agent。"""

    identity = IdentityStore()
    # 创建两个独立组织，各有一个 owner
    owner_a = identity.register_user("orga-owner@example.com", "Owner A", "pass")
    owner_b = identity.register_user("orgb-owner@example.com", "Owner B", "pass")
    org_a = identity.create_organization(owner_a.user_id, "组织 A")
    org_b = identity.create_organization(owner_b.user_id, "组织 B")

    from apps.api.app.services.agent_store import AgentStore
    agent_store = AgentStore(identity=identity)

    # 组织 A 的 Agent
    agent_a = agent_store.create_agent(owner_a.user_id, org_a.org_id, "Agent A", "")

    # 组织 B 的 owner 不能查看组织 A 的 Agent 列表
    agents_in_b = agent_store.list_agents(actor_user_id=owner_b.user_id, org_id=org_b.org_id)
    assert all(a.agent_id != agent_a.agent_id for a in agents_in_b)

    # 组织 B 的 owner 不能直接读取组织 A 的 Workspace
    try:
        agent_store.get_workspace(actor_user_id=owner_b.user_id, agent_id=agent_a.agent_id)
        assert False, "跨组织应拒绝访问 Workspace"
    except PermissionError:
        pass


def test_cross_org_skill_isolation() -> None:
    """验证 Skill 按组织隔离：组织 A 的 Skill 对组织 B 的 Agent 不可见。"""

    identity = IdentityStore()
    owner_a = identity.register_user("skill-orga@example.com", "Owner A", "pass")
    owner_b = identity.register_user("skill-orgb@example.com", "Owner B", "pass")
    org_a = identity.create_organization(owner_a.user_id, "Skill Org A")
    org_b = identity.create_organization(owner_b.user_id, "Skill Org B")

    from apps.api.app.services.skill_store import SkillStore
    from apps.api.app.services.agent_store import AgentStore
    agent_store = AgentStore(identity=identity)
    skill_store = SkillStore(identity=identity, agents=agent_store)

    agent_b = agent_store.create_agent(owner_b.user_id, org_b.org_id, "Agent B", "")

    # 组织 A 注册 Skill
    skill = skill_store.register_skill(
        actor_user_id=owner_a.user_id,
        org_id=org_a.org_id,
        scope="organization",
        content="---\nname: org-a-skill\ndescription: 组织 A 专属\n---\n\n内部知识。\n",
    )
    # Agent B 看不到组织 A 的 Skill
    summaries = skill_store.list_allowed_skill_summaries(
        actor_user_id=owner_b.user_id, agent_id=agent_b.agent_id
    )
    assert all(s["name"] != "org-a-skill" for s in summaries)

    # Agent B 不能读取组织 A 的 Skill 全文（需 agent_id 参数）
    try:
        skill_store.get_skill_content(
            actor_user_id=owner_b.user_id,
            agent_id=agent_b.agent_id,
            skill_id=skill.skill_id,
        )
        assert False, "跨组织应拒绝读取 Skill 全文"
    except PermissionError:
        pass


def test_cross_org_mcp_isolation() -> None:
    """验证 MCP Server 按组织隔离。"""

    identity = IdentityStore()
    owner_a = identity.register_user("mcp-orga@example.com", "Owner A", "pass")
    owner_b = identity.register_user("mcp-orgb@example.com", "Owner B", "pass")
    org_a = identity.create_organization(owner_a.user_id, "MCP Org A")
    org_b = identity.create_organization(owner_b.user_id, "MCP Org B")

    from apps.api.app.services.mcp_store import MCPStore
    from apps.api.app.services.agent_store import AgentStore
    from apps.api.app.domain.mcp import MCPTransport
    agent_store = AgentStore(identity=identity)
    mcp_store = MCPStore(identity=identity, agents=agent_store)

    agent_b = agent_store.create_agent(owner_b.user_id, org_b.org_id, "Agent B", "")

    # 组织 A 注册 MCP Server
    server = mcp_store.register_server(
        actor_user_id=owner_a.user_id,
        org_id=org_a.org_id,
        name="OrgA MCP",
        transport=MCPTransport.HTTP,
        url="http://localhost:18080/mcp",
    )

    # 组织 B 看不到组织 A 的 MCP Server
    servers = mcp_store.list_servers(actor_user_id=owner_b.user_id, org_id=org_b.org_id)
    assert all(s.server_id != server.server_id for s in servers)


def test_cross_org_knowledge_isolation() -> None:
    """验证知识库跨组织隔离：不能跨组织检索文档。"""

    identity = IdentityStore()
    owner_a = identity.register_user("kb-orga@example.com", "Owner A", "pass")
    owner_b = identity.register_user("kb-orgb@example.com", "Owner B", "pass")
    org_a = identity.create_organization(owner_a.user_id, "KB Org A")
    org_b = identity.create_organization(owner_b.user_id, "KB Org B")

    from apps.api.app.services.knowledge_store import KnowledgeStore
    knowledge = KnowledgeStore(identity=identity)

    kb_a = knowledge.create_knowledge_base(owner_a.user_id, org_a.org_id, "组织A知识库", "")
    knowledge.upload_document(
        actor_user_id=owner_a.user_id,
        kb_id=kb_a.kb_id,
        title="机密文档",
        content="本内容仅供组织 A 成员访问。",
        chunk_size=200,
    )

    # 组织 B 用户不能检索组织 A 的知识库
    try:
        knowledge.search(
            actor_user_id=owner_b.user_id,
            kb_id=kb_a.kb_id,
            query="机密",
            limit=5,
        )
        assert False, "跨组织应拒绝检索知识库"
    except PermissionError:
        pass


def test_cross_org_memory_isolation() -> None:
    """验证 Memory 按组织隔离：Agent 只能访问同组织记忆。"""

    identity = IdentityStore()
    owner_a = identity.register_user("mem-orga@example.com", "Owner A", "pass")
    owner_b = identity.register_user("mem-orgb@example.com", "Owner B", "pass")
    org_a = identity.create_organization(owner_a.user_id, "Mem Org A")
    org_b = identity.create_organization(owner_b.user_id, "Mem Org B")

    from apps.api.app.services.memory_store import MemoryStore
    from apps.api.app.services.agent_store import AgentStore
    agent_store = AgentStore(identity=identity)
    memory_store = MemoryStore(identity=identity, agents=agent_store)

    agent_a = agent_store.create_agent(owner_a.user_id, org_a.org_id, "Agent A", "")
    agent_b = agent_store.create_agent(owner_b.user_id, org_b.org_id, "Agent B", "")

    # 组织 A Agent 写入记忆
    memory_store.create_memory(
        actor_user_id=owner_a.user_id,
        agent_id=agent_a.agent_id,
        memory_type="fact",
        content="组织 A 内部数据",
        summary="内部数据",
        confidence=0.95,
        source="test",
    )

    # 组织 B 用户不能读取组织 A Agent 的记忆
    try:
        memory_store.list_memories(
            actor_user_id=owner_b.user_id,
            agent_id=agent_a.agent_id,
        )
        assert False, "跨组织应拒绝读取 Memory"
    except PermissionError:
        pass

    # 组织 B Agent 自己的记忆为空
    own_memories = memory_store.list_memories(
        actor_user_id=owner_b.user_id,
        agent_id=agent_b.agent_id,
    )
    assert len(own_memories) == 0


def test_rbac_viewer_cannot_create_resources() -> None:
    """验证 viewer 不能创建任何写操作资源。"""

    identity = IdentityStore()
    owner = identity.register_user("rbac-owner@example.com", "Owner", "pass")
    viewer = identity.register_user("rbac-viewer@example.com", "Viewer", "pass")
    org = identity.create_organization(owner.user_id, "RBAC Org")
    identity.add_member(
        actor_user_id=owner.user_id,
        org_id=org.org_id,
        target_user_id=viewer.user_id,
        role=OrganizationRole.VIEWER,
    )

    from apps.api.app.services.agent_store import AgentStore
    agent_store = AgentStore(identity=identity)

    # Viewer 不能创建 Agent
    try:
        agent_store.create_agent(viewer.user_id, org.org_id, "非法 Agent", "")
        assert False, "viewer 不能创建 Agent"
    except PermissionError:
        pass

    # Viewer 不能创建 Workflow
    from apps.api.app.services.workflow_store import WorkflowStore
    # 先创建 owner 的 agent 作为合法目标
    agent = agent_store.create_agent(owner.user_id, org.org_id, "Owner Agent", "")
    workflow_store = WorkflowStore(identity=identity, agents=agent_store)
    try:
        workflow_store.create_workflow(
            viewer.user_id, agent.agent_id, "非法 Workflow", "",
            {"version": "1.0", "nodes": [], "edges": []},
        )
        assert False, "viewer 不能创建 Workflow"
    except PermissionError:
        pass


def test_rbac_developer_can_create_but_not_manage() -> None:
    """验证 developer 可创建资源但不能管理（如审计日志）。"""

    identity = IdentityStore()
    owner = identity.register_user("dev-owner@example.com", "Owner", "pass")
    dev = identity.register_user("dev-user@example.com", "Developer", "pass")
    org = identity.create_organization(owner.user_id, "Dev Org")
    team = identity.create_team(owner.user_id, org.org_id, "Dev Team")
    identity.add_member(
        actor_user_id=owner.user_id,
        org_id=org.org_id,
        target_user_id=dev.user_id,
        role=OrganizationRole.DEVELOPER,
        team_ids=[team.team_id],
    )

    from apps.api.app.services.agent_store import AgentStore
    agent_store = AgentStore(identity=identity)

    # Developer 可以创建 Agent
    agent = agent_store.create_agent(dev.user_id, org.org_id, "Dev Agent", "")
    assert agent.name == "Dev Agent"

    # Developer 不能读取审计日志
    try:
        identity.list_audit_logs(actor_user_id=dev.user_id, org_id=org.org_id)
        assert False, "developer 不能读审计日志"
    except PermissionError:
        pass

    # Developer 不能管理团队成员
    try:
        identity.add_member(
            actor_user_id=dev.user_id,
            org_id=org.org_id,
            target_user_id=owner.user_id,
            role=OrganizationRole.VIEWER,
        )
        assert False, "developer 不能管理成员"
    except PermissionError:
        pass


def test_provider_credential_masking() -> None:
    """验证 Provider API Key 在响应中被脱敏处理。"""

    client = TestClient(app)
    suffix = uuid4().hex

    owner_response = client.post(
        "/identity/users/register",
        json={
            "email": f"cred-owner-{suffix}@example.com",
            "display_name": "Cred Owner",
            "password": "password123",
        },
    )
    owner_user_id = owner_response.json()["user_id"]

    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Cred Org"},
    )
    org_id = org_response.json()["org_id"]

    # 创建 Provider 并验证 Key 脱敏
    provider_response = client.post(
        "/model-providers",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "provider_key": "openai",
            "display_name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-proj-secret-key-1234567890abcdef",
            "models": ["gpt-4"],
            "default_model": "gpt-4",
        },
    )
    assert provider_response.status_code == 200
    data = provider_response.json()
    assert "api_key_masked" in data
    # 验证脱敏后的 Key 格式正确（不包含原始密钥）
    masked = data["api_key_masked"]
    assert "sk-" in masked
    assert "..." in masked
    assert "sk-proj-secret-key-1234567890abcdef" not in masked
    # 确保原始密钥不出现在整个响应中
    assert "sk-proj-secret-key-1234567890abcdef" not in str(data)


def test_audit_log_records_all_actions() -> None:
    """验证审计日志记录了所有关键操作。"""

    client = TestClient(app)
    suffix = uuid4().hex

    # 注册和组织创建
    owner_response = client.post(
        "/identity/users/register",
        json={
            "email": f"audit-owner-{suffix}@example.com",
            "display_name": "Audit Owner",
            "password": "password123",
        },
    )
    owner_user_id = owner_response.json()["user_id"]

    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Audit Org"},
    )
    org_id = org_response.json()["org_id"]

    # 群组创建
    client.post(
        f"/identity/organizations/{org_id}/teams",
        json={"actor_user_id": owner_user_id, "name": "Audit Team"},
    )

    # 添加成员
    viewer_response = client.post(
        "/identity/users/register",
        json={
            "email": f"audit-viewer-{suffix}@example.com",
            "display_name": "Audit Viewer",
            "password": "password123",
        },
    )
    viewer_id = viewer_response.json()["user_id"]

    client.post(
        f"/identity/organizations/{org_id}/members",
        json={
            "actor_user_id": owner_user_id,
            "target_user_id": viewer_id,
            "role": "viewer",
        },
    )

    # 查看审计日志
    audit_response = client.get(
        f"/identity/organizations/{org_id}/audit-logs",
        params={"actor_user_id": owner_user_id},
    )
    assert audit_response.status_code == 200
    logs = audit_response.json()

    # 应至少有：组织创建、群组创建、成员添加
    # 注：user.registered 是平台级事件（org_id=""），不在组织审计日志中
    actions = [log["action"] for log in logs]
    assert "organization.created" in actions
    assert "team.created" in actions
    assert "member.joined" in actions


def test_session_isolation_between_orgs() -> None:
    """验证 Session 跨组织隔离：组织 A 用户不能访问组织 B Agent 的 Session。"""

    identity = IdentityStore()
    owner_a = identity.register_user("sess-orga@example.com", "Owner A", "pass")
    owner_b = identity.register_user("sess-orgb@example.com", "Owner B", "pass")
    org_a = identity.create_organization(owner_a.user_id, "Session Org A")
    org_b = identity.create_organization(owner_b.user_id, "Session Org B")

    from apps.api.app.services.agent_store import AgentStore
    from apps.api.app.services.session_store import SessionStore
    agent_store = AgentStore(identity=identity)
    session_store = SessionStore(agents=agent_store)

    agent_a = agent_store.create_agent(owner_a.user_id, org_a.org_id, "Agent A", "")

    # 组织 A 创建 Session
    session_a = session_store.create_session(
        actor_user_id=owner_a.user_id,
        agent_id=agent_a.agent_id,
        queue_mode="queue",
    )
    session_store.append_message(
        actor_user_id=owner_a.user_id,
        session_id=session_a.session_id,
        role="user",
        content="秘密消息",
    )

    # 组织 B 用户无法访问组织 A 的 Session
    try:
        session_store.list_sessions(
            actor_user_id=owner_b.user_id,
            agent_id=agent_a.agent_id,
        )
        assert False, "跨组织应拒绝访问 Session"
    except PermissionError:
        pass
