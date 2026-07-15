"""多租户联合集成测试。

验证 DEVELOPMENT_PLAN.md Module 18 要求的：
- 多用户、多组织、多 Agent 联调
- 资源隔离无越权
- 多租户并发操作安全性
"""
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import app


def _auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/identity/users/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


def test_multi_org_multi_agent_concurrent_resources() -> None:
    """验证多个组织下的多个 Agent 各自拥有独立资源，互不干扰。"""

    client = TestClient(app)
    suffix = uuid4().hex

    # === 组织 A ===
    owner_a_email = f"mt-owner-a-{suffix}@example.com"
    owner_a_resp = client.post(
        "/identity/users/register",
        json={"email": owner_a_email, "display_name": "Owner A", "password": "password123"},
    )
    owner_a = owner_a_resp.json()["user_id"]
    org_a_resp = client.post("/identity/organizations", json={"creator_user_id": owner_a, "name": "MT Org A"})
    org_a = org_a_resp.json()["org_id"]
    team_a_resp = client.post(
        f"/identity/organizations/{org_a}/teams",
        json={"actor_user_id": owner_a, "name": "Team A"},
    )
    team_a = team_a_resp.json()["team_id"]
    owner_a_headers = _auth_headers(client, owner_a_email)

    # === 组织 B ===
    owner_b_email = f"mt-owner-b-{suffix}@example.com"
    owner_b_resp = client.post(
        "/identity/users/register",
        json={"email": owner_b_email, "display_name": "Owner B", "password": "password123"},
    )
    owner_b = owner_b_resp.json()["user_id"]
    org_b_resp = client.post("/identity/organizations", json={"creator_user_id": owner_b, "name": "MT Org B"})
    org_b = org_b_resp.json()["org_id"]
    owner_b_headers = _auth_headers(client, owner_b_email)

    # === 组织 A 创建 Agent A1, A2 ===
    agent_a1_resp = client.post(
        "/agents",
        json={"actor_user_id": owner_a, "org_id": org_a, "team_id": team_a, "name": "Agent A1", "description": "A1"},
        headers=owner_a_headers,
    )
    agent_a1 = agent_a1_resp.json()["agent_id"]

    agent_a2_resp = client.post(
        "/agents",
        json={"actor_user_id": owner_a, "org_id": org_a, "team_id": team_a, "name": "Agent A2", "description": "A2"},
        headers=owner_a_headers,
    )
    agent_a2 = agent_a2_resp.json()["agent_id"]

    # === 组织 B 创建 Agent B1 ===
    agent_b1_resp = client.post(
        "/agents",
        json={"actor_user_id": owner_b, "org_id": org_b, "name": "Agent B1", "description": "B1"},
        headers=owner_b_headers,
    )
    agent_b1 = agent_b1_resp.json()["agent_id"]

    # === 组织 A 为 A1 配置 Skill ===
    skill_resp = client.post(
        "/skills",
        json={
            "actor_user_id": owner_a,
            "org_id": org_a,
            "scope": "organization",
            "content": "---\nname: a1-skill\ndescription: A1 专属 Skill\n---\n\n专属于 A1 的知识。\n",
            "team_id": team_a,
            "agent_id": agent_a1,
        },
    )
    skill_id = skill_resp.json()["skill_id"]
    client.put(
        f"/skills/agents/{agent_a1}/policy",
        json={"actor_user_id": owner_a, "skill_id": skill_id, "allowed": True},
    )

    # === 组织 A 为 A1 写入 Memory ===
    client.post(
        "/memory",
        json={
            "actor_user_id": owner_a,
            "agent_id": agent_a1,
            "memory_type": "preference",
            "content": "A1 偏好中文输出",
            "summary": "A1 中文偏好",
            "confidence": 0.9,
            "source": "test",
        },
    )

    # === 组织 A 为 A1 创建 Session ===
    session_resp = client.post(
        "/sessions",
        json={"actor_user_id": owner_a, "agent_id": agent_a1, "queue_mode": "queue"},
    )
    session_a1 = session_resp.json()["session_id"]

    # === 验证 Agent A1 的资源对 B1 不可见 ===
    # B1 无法看到 A1 的 Skill
    skill_summaries_b1 = client.get(
        f"/skills/agents/{agent_b1}/summaries",
        params={"actor_user_id": owner_b},
    )
    assert skill_summaries_b1.status_code == 200
    assert all(s["name"] != "a1-skill" for s in skill_summaries_b1.json())

    # B1 无法看到 A1 的 Memory（跨组织应被拒）
    memory_list_b1 = client.get(
        "/memory",
        params={"actor_user_id": owner_b, "agent_id": agent_a1},
    )
    assert memory_list_b1.status_code == 403

    # B1 无法看到 A1 的 Session（跨组织应被拒）
    session_list_b1 = client.get(
        "/sessions",
        params={"agent_id": agent_a1, "actor_user_id": owner_b},
    )
    assert session_list_b1.status_code == 403

    # === 验证组织 A 内部的 Agent A2 和 A1 在自己的资源内独立 ===
    # A2 应该没有 A1 已授权的 Skill
    a2_skill_summaries = client.get(
        f"/skills/agents/{agent_a2}/summaries",
        params={"actor_user_id": owner_a},
    )
    assert a2_skill_summaries.status_code == 200
    assert all(s["name"] != "a1-skill" for s in a2_skill_summaries.json())

    # A2 应该没有 A1 的 Session
    a2_sessions = client.get(
        "/sessions",
        params={"agent_id": agent_a2, "actor_user_id": owner_a},
    )
    assert a2_sessions.status_code == 200
    assert a2_sessions.json() == []


def test_memory_route_distinguishes_missing_agent_from_cross_org_access() -> None:
    """Memory routes return 403 for a foreign Agent and 404 only when absent."""

    client = TestClient(app)
    suffix = uuid4().hex

    owner_a_email = f"memory-owner-a-{suffix}@example.com"
    owner_a = client.post(
        "/identity/users/register",
        json={"email": owner_a_email, "display_name": "Owner A", "password": "password123"},
    ).json()["user_id"]
    org_a = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_a, "name": "Memory Org A"},
    ).json()["org_id"]
    owner_a_headers = _auth_headers(client, owner_a_email)
    agent_a = client.post(
        "/agents",
        json={"actor_user_id": owner_a, "org_id": org_a, "name": "Memory Agent A", "description": ""},
        headers=owner_a_headers,
    ).json()["agent_id"]

    owner_b = client.post(
        "/identity/users/register",
        json={"email": f"memory-owner-b-{suffix}@example.com", "display_name": "Owner B", "password": "password123"},
    ).json()["user_id"]

    foreign_response = client.get(
        "/memory", params={"actor_user_id": owner_b, "agent_id": agent_a}
    )
    assert foreign_response.status_code == 403
    assert foreign_response.json()["detail"] == "Forbidden"

    missing_response = client.get(
        "/memory", params={"actor_user_id": owner_b, "agent_id": "agt_missing"}
    )
    assert missing_response.status_code == 404


def test_session_routes_distinguish_missing_session_from_cross_org_access() -> None:
    """Existing foreign sessions return 403, while unknown IDs remain 404."""

    client = TestClient(app)
    suffix = uuid4().hex

    owner_a_email = f"session-owner-a-{suffix}@example.com"
    owner_a = client.post(
        "/identity/users/register",
        json={"email": owner_a_email, "display_name": "Owner A", "password": "password123"},
    ).json()["user_id"]
    org_a = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_a, "name": "Session Org A"},
    ).json()["org_id"]
    owner_a_headers = _auth_headers(client, owner_a_email)
    agent_a = client.post(
        "/agents",
        json={"actor_user_id": owner_a, "org_id": org_a, "name": "Session Agent A", "description": ""},
        headers=owner_a_headers,
    ).json()["agent_id"]
    session_a = client.post(
        "/sessions",
        json={"actor_user_id": owner_a, "agent_id": agent_a, "queue_mode": "queue"},
    ).json()["session_id"]

    owner_b = client.post(
        "/identity/users/register",
        json={"email": f"session-owner-b-{suffix}@example.com", "display_name": "Owner B", "password": "password123"},
    ).json()["user_id"]

    foreign_responses = [
        client.get(f"/sessions/{session_a}", params={"actor_user_id": owner_b}),
        client.get(f"/sessions/{session_a}/messages", params={"actor_user_id": owner_b}),
        client.post(
            f"/sessions/{session_a}/messages",
            json={"actor_user_id": owner_b, "role": "user", "content": "do not write"},
        ),
        client.post(
            f"/sessions/{session_a}/compact",
            json={"actor_user_id": owner_b, "summary": "do not compact"},
        ),
        client.get("/sessions", params={"agent_id": agent_a, "actor_user_id": owner_b}),
    ]
    for response in foreign_responses:
        assert response.status_code == 403
        assert response.json() == {"detail": "Forbidden"}

    missing_response = client.get(
        "/sessions/ses_missing", params={"actor_user_id": owner_b}
    )
    assert missing_response.status_code == 404


def test_multi_tenant_workflow_isolation() -> None:
    """验证不同组织的 Workflow 完全隔离。"""

    client = TestClient(app)
    suffix = uuid4().hex

    # === 组织 A ===
    owner_a_email = f"wf-iso-a-{suffix}@example.com"
    owner_a_resp = client.post(
        "/identity/users/register",
        json={"email": owner_a_email, "display_name": "WF Owner A", "password": "password123"},
    )
    owner_a = owner_a_resp.json()["user_id"]
    org_a_resp = client.post("/identity/organizations", json={"creator_user_id": owner_a, "name": "WF Org A"})
    org_a = org_a_resp.json()["org_id"]
    owner_a_headers = _auth_headers(client, owner_a_email)
    agent_a_resp = client.post(
        "/agents",
        json={"actor_user_id": owner_a, "org_id": org_a, "name": "WF Agent A", "description": ""},
        headers=owner_a_headers,
    )
    agent_a = agent_a_resp.json()["agent_id"]

    # === 组织 B ===
    owner_b_email = f"wf-iso-b-{suffix}@example.com"
    owner_b_resp = client.post(
        "/identity/users/register",
        json={"email": owner_b_email, "display_name": "WF Owner B", "password": "password123"},
    )
    owner_b = owner_b_resp.json()["user_id"]
    org_b_resp = client.post("/identity/organizations", json={"creator_user_id": owner_b, "name": "WF Org B"})
    org_b = org_b_resp.json()["org_id"]
    owner_b_headers = _auth_headers(client, owner_b_email)
    agent_b_resp = client.post(
        "/agents",
        json={"actor_user_id": owner_b, "org_id": org_b, "name": "WF Agent B", "description": ""},
        headers=owner_b_headers,
    )
    agent_b = agent_b_resp.json()["agent_id"]

    # === 组织 A 创建并执行 Workflow ===
    wf_a_resp = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_a,
            "agent_id": agent_a,
            "name": "WF A",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [{"source": "start", "target": "end"}],
            },
        },
    )
    wf_a_id = wf_a_resp.json()["workflow_id"]
    version_a_resp = client.post(f"/workflows/{wf_a_id}/publish", json={"actor_user_id": owner_a})
    version_a_id = version_a_resp.json()["version_id"]

    run_a_resp = client.post(
        "/workflow-runs",
        json={
            "version_id": version_a_id,
            "input_data": {"text": "hello"},
            "async_mode": False,
        },
        headers=owner_a_headers,
    )
    assert run_a_resp.status_code == 200
    run_a_id = run_a_resp.json()["run_id"]

    # === 组织 B 不能查看组织 A 的 Workflow ===
    wf_list_b = client.get("/workflows", params={"actor_user_id": owner_b, "org_id": org_b})
    assert wf_list_b.status_code == 200
    assert wf_list_b.json() == []

    # 组织 B 不能查看组织 A 的执行记录
    run_list_b = client.get("/workflow-runs", params={"actor_user_id": owner_b, "org_id": org_b})
    assert run_list_b.status_code == 200
    assert run_list_b.json() == []

    # 组织 B 不能直接读取组织 A 的执行详情（跨组织被拒）
    run_detail_b = client.get(
        f"/workflow-runs/{run_a_id}/nodes",
        params={"actor_user_id": owner_b},
    )
    assert run_detail_b.status_code == 403


def test_multi_tenant_rate_limit_per_org() -> None:
    """验证限流按组织维度计数，一个组织的请求不会影响其他组织。"""

    from apps.api.app.gateway.rate_limiter import LocalTokenBucketRateLimiter

    # 创建两个独立的限流器分别代表两个组织
    limiter_a = LocalTokenBucketRateLimiter(default_capacity=5, default_refill_rate=1.0)
    limiter_b = LocalTokenBucketRateLimiter(default_capacity=5, default_refill_rate=1.0)

    # 组织 A 耗尽自己的 tokens
    for _ in range(5):
        assert limiter_a.allow(key="org-a") is True
    assert limiter_a.allow(key="org-a") is False  # 组织 A 被限流

    # 组织 B 不受影响
    for _ in range(5):
        assert limiter_b.allow(key="org-b") is True
    assert limiter_b.allow(key="org-b") is False  # 组织 B 也耗尽

    # 验证多维限流 key 正确隔离（同一个 limiter 下不同 key 互不影响）
    shared_limiter = LocalTokenBucketRateLimiter(default_capacity=10, default_refill_rate=100.0)
    # org-a 消费全部 tokens
    for _ in range(10):
        assert shared_limiter.allow(key="org:org-a:provider:openai:model:gpt-4") is True
    assert shared_limiter.allow(key="org:org-a:provider:openai:model:gpt-4") is False

    # org-b 有独立的桶，不受影响
    assert shared_limiter.allow(key="org:org-b:provider:openai:model:gpt-4") is True
