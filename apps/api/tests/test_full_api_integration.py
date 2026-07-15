"""完整 API 联调测试。

该测试覆盖前端全链路联调工作台依赖的主要后端接口，确保用户、组织、Agent、
Session、Skill、MCP、Memory、Context、Gateway 和 Workflow Run 能按顺序协同工作。
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.gateway.llm import LLMCallResponse, OpenAICompatibleProvider
from apps.api.app.main import app

VALID_WORKFLOW_DEFINITION = {
    "version": "1.0",
    "nodes": [
        {"id": "start", "type": "start", "config": {}},
        {
            "id": "llm",
            "type": "llm",
            "config": {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "prompt": "请总结输入，并给出下一步建议。",
            },
        },
        {"id": "end", "type": "end", "config": {}},
    ],
    "edges": [
        {"source": "start", "target": "llm"},
        {"source": "llm", "target": "end"},
    ],
}


def test_full_api_integration_chain(monkeypatch) -> None:
    """验证前端全模块联调依赖的 API 主链路。"""

    def _generate_without_network(
        _provider: OpenAICompatibleProvider, request
    ) -> LLMCallResponse:
        return LLMCallResponse(
            text="[fake-llm] gateway response",
            provider=request.provider,
            model=request.model,
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    monkeypatch.setattr(OpenAICompatibleProvider, "generate", _generate_without_network)

    client = TestClient(app)
    suffix = uuid4().hex

    owner_email = f"full-owner-{suffix}@example.com"
    owner_response = client.post(
        "/identity/users/register",
        json={
            "email": owner_email,
            "display_name": "Owner",
            "password": "password123",
        },
    )
    assert owner_response.status_code == 200
    owner_user_id = owner_response.json()["user_id"]

    viewer_response = client.post(
        "/identity/users/register",
        json={
            "email": f"full-viewer-{suffix}@example.com",
            "display_name": "Viewer",
            "password": "password123",
        },
    )
    assert viewer_response.status_code == 200
    viewer_user_id = viewer_response.json()["user_id"]

    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Full API 组织"},
    )
    assert org_response.status_code == 200
    org_id = org_response.json()["org_id"]
    owner_login = client.post(
        "/identity/users/login",
        json={"email": owner_email, "password": "password123"},
    )
    assert owner_login.status_code == 200
    owner_headers = {
        "Authorization": f"Bearer {owner_login.json()['token']['access_token']}"
    }

    team_response = client.post(
        f"/identity/organizations/{org_id}/teams",
        json={"actor_user_id": owner_user_id, "name": "联调团队"},
    )
    assert team_response.status_code == 200
    team_id = team_response.json()["team_id"]

    member_response = client.post(
        f"/identity/organizations/{org_id}/members",
        json={
            "actor_user_id": owner_user_id,
            "target_user_id": viewer_user_id,
            "role": "viewer",
            "team_ids": [team_id],
        },
    )
    assert member_response.status_code == 200
    viewer_login = client.post(
        "/identity/users/login",
        json={"email": f"full-viewer-{suffix}@example.com", "password": "password123"},
    )
    assert viewer_login.status_code == 200
    viewer_headers = {
        "Authorization": f"Bearer {viewer_login.json()['token']['access_token']}"
    }

    provider_response = client.post(
        "/model-providers",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "provider_key": "deepseek",
            "display_name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-test-provider-key",
            "models": ["deepseek-chat", "deepseek-reasoner"],
            "default_model": "deepseek-chat",
        },
    )
    assert provider_response.status_code == 200
    masked_api_key = provider_response.json()["api_key_masked"]
    assert masked_api_key == "sk-tes...-key"
    assert masked_api_key != "sk-test-provider-key"

    provider_list_response = client.get(
        "/model-providers",
        params={"actor_user_id": owner_user_id, "org_id": org_id},
    )
    assert provider_list_response.status_code == 200
    assert provider_list_response.json()[0]["provider_key"] == "deepseek"

    agent_response = client.post(
        "/agents",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "team_id": team_id,
            "name": "Full API Agent",
            "description": "用于完整 API 联调。",
        },
        headers=owner_headers,
    )
    assert agent_response.status_code == 200
    agent_id = agent_response.json()["agent_id"]

    agent_list_response = client.get(
        "/agents",
        params={"org_id": org_id, "actor_user_id": owner_user_id},
    )
    assert agent_list_response.status_code == 200
    assert agent_list_response.json()[0]["agent_id"] == agent_id

    workspace_response = client.put(
        f"/agents/{agent_id}/workspace/file",
        json={
            "actor_user_id": owner_user_id,
            "file_kind": "AGENTS.md",
            "content": "# AGENTS\n\n请使用中文输出结论。\n",
        },
    )
    assert workspace_response.status_code == 200
    assert "AGENTS.md" in workspace_response.json()["files"]

    session_response = client.post(
        "/sessions",
        json={"actor_user_id": owner_user_id, "agent_id": agent_id, "queue_mode": "queue"},
    )
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    session_list_response = client.get(
        "/sessions",
        params={"agent_id": agent_id, "actor_user_id": owner_user_id},
    )
    assert session_list_response.status_code == 200
    assert session_list_response.json()[0]["session_id"] == session_id

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={
            "actor_user_id": owner_user_id,
            "role": "user",
            "content": "请完成完整 API 联调。",
        },
    )
    assert message_response.status_code == 200

    compact_response = client.post(
        f"/sessions/{session_id}/compact",
        json={"actor_user_id": owner_user_id, "summary": "用户要求完成完整 API 联调。"},
    )
    assert compact_response.status_code == 200

    skill_response = client.post(
        "/skills",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "scope": "organization",
            "content": (
                "---\n"
                "name: workflow-reviewer\n"
                "description: 检查工作流结构并给出改进建议\n"
                "---\n\n"
                "优先检查节点顺序、输入输出和错误处理。\n"
            ),
            "team_id": team_id,
            "agent_id": agent_id,
        },
    )
    assert skill_response.status_code == 200
    skill_id = skill_response.json()["skill_id"]

    skill_policy_response = client.put(
        f"/skills/agents/{agent_id}/policy",
        json={"actor_user_id": owner_user_id, "skill_id": skill_id, "allowed": True},
    )
    assert skill_policy_response.status_code == 200

    skill_summaries_response = client.get(
        f"/skills/agents/{agent_id}/summaries",
        params={"actor_user_id": owner_user_id},
    )
    assert skill_summaries_response.status_code == 200
    assert skill_summaries_response.json()[0]["name"] == "workflow-reviewer"

    skill_list_response = client.get(
        "/skills",
        params={"org_id": org_id, "actor_user_id": owner_user_id},
    )
    assert skill_list_response.status_code == 200
    assert skill_list_response.json()[0]["skill_id"] == skill_id

    mcp_server_response = client.post(
        "/mcp/servers",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "name": "知识库 MCP",
            "transport": "http",
            "url": "http://localhost:18080/mcp",
        },
    )
    assert mcp_server_response.status_code == 200
    server_id = mcp_server_response.json()["server_id"]

    mcp_server_list_response = client.get(
        "/mcp/servers",
        params={"org_id": org_id, "actor_user_id": owner_user_id},
    )
    assert mcp_server_list_response.status_code == 200
    assert mcp_server_list_response.json()[0]["server_id"] == server_id

    mcp_tool_response = client.post(
        f"/mcp/servers/{server_id}/tools",
        json={
            "actor_user_id": owner_user_id,
            "name": "search_docs",
            "description": "检索内部知识库文档",
            "input_schema": {"type": "object"},
            "risk_level": "low",
        },
    )
    assert mcp_tool_response.status_code == 200
    tool_id = mcp_tool_response.json()["tool_id"]

    mcp_policy_response = client.put(
        f"/mcp/agents/{agent_id}/policy",
        json={"actor_user_id": owner_user_id, "server_id": server_id, "allowed": True},
    )
    assert mcp_policy_response.status_code == 200

    can_call_response = client.get(
        f"/mcp/agents/{agent_id}/tools/{tool_id}/can-call",
        params={"actor_user_id": owner_user_id},
    )
    assert can_call_response.status_code == 200

    memory_response = client.post(
        "/memory",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "memory_type": "preference",
            "content": "用户偏好中文、先给结论。",
            "summary": "用户偏好中文并先给结论。",
            "confidence": 0.98,
            "source": "api-test",
        },
    )
    assert memory_response.status_code == 200
    memory_id = memory_response.json()["memory_id"]

    memory_list_response = client.get(
        "/memory",
        params={"actor_user_id": owner_user_id, "agent_id": agent_id},
    )
    assert memory_list_response.status_code == 200
    assert memory_list_response.json()[0]["memory_id"] == memory_id

    memory_recall_response = client.post(
        "/memory/recall",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "query": "中文 结论",
            "limit": 5,
        },
    )
    assert memory_recall_response.status_code == 200
    assert len(memory_recall_response.json()) >= 1

    context_response = client.get(
        f"/context/sessions/{session_id}/assemble",
        params={
            "actor_user_id": owner_user_id,
            "current_input": "请输出完整联调报告",
            "token_budget": 4096,
        },
    )
    assert context_response.status_code == 200
    section_names = [section["name"] for section in context_response.json()["sections"]]
    assert {
        "workspace",
        "skill_summaries",
        "memories",
        "append_only_messages",
        "current_input",
    }.issubset(set(section_names))

    gateway_response = client.post(
        "/gateway/llm/generate",
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "prompt": "请用一句话总结全链路联调状态。",
            "parameters": {"temperature": 0},
        },
        headers=owner_headers,
    )
    assert gateway_response.status_code == 200
    assert gateway_response.json()["provider"] == "deepseek"

    gateway_logs_response = client.get("/gateway/llm/logs", headers=owner_headers)
    assert gateway_logs_response.status_code == 200
    assert len(gateway_logs_response.json()) >= 1

    workflow_response = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "name": "完整 API 联调工作流",
            "description": "覆盖工作流发布和执行。",
            "draft_definition": VALID_WORKFLOW_DEFINITION,
        },
    )
    assert workflow_response.status_code == 200
    workflow_id = workflow_response.json()["workflow_id"]

    workflow_list_response = client.get(
        "/workflows",
        params={"actor_user_id": owner_user_id, "org_id": org_id},
    )
    assert workflow_list_response.status_code == 200
    assert workflow_list_response.json()[0]["workflow_id"] == workflow_id

    version_response = client.post(
        f"/workflows/{workflow_id}/publish",
        json={"actor_user_id": owner_user_id},
    )
    assert version_response.status_code == 200
    version_id = version_response.json()["version_id"]

    run_response = client.post(
        "/workflow-runs",
        json={
            "version_id": version_id,
            "input_data": {"text": "hello"},
            "async_mode": False,
        },
        headers=owner_headers,
    )
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "succeeded"
    run_id = run_response.json()["run_id"]

    run_list_response = client.get(
        "/workflow-runs",
        params={"actor_user_id": owner_user_id, "org_id": org_id},
    )
    assert run_list_response.status_code == 200
    assert run_list_response.json()[0]["run_id"] == run_id

    node_runs_response = client.get(
        f"/workflow-runs/{run_id}/nodes",
        params={"actor_user_id": owner_user_id},
    )
    assert node_runs_response.status_code == 200
    assert [node_run["node_id"] for node_run in node_runs_response.json()] == [
        "start",
        "llm",
        "end",
    ]

    forbidden_response = client.post(
        "/agents",
        json={
            "actor_user_id": viewer_user_id,
            "org_id": org_id,
            "name": "非法 Agent",
            "description": "viewer 不应创建该资源。",
        },
        headers=viewer_headers,
    )
    assert forbidden_response.status_code == 403

    audit_response = client.get(
        f"/identity/organizations/{org_id}/audit-logs",
        params={"actor_user_id": owner_user_id},
    )
    assert audit_response.status_code == 200
    assert len(audit_response.json()) >= 1
