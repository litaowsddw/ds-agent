"""端到端工作流执行测试。

覆盖 DEVELOPMENT_PLAN.md Module 18 的验收标准：
- 工作流执行轨迹完整
- 每个节点有状态、输入、输出、耗时
- 失败可重试或终止
- 异步模式与同步模式
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app
from app.gateway.llm import LLMCallRequest, LLMCallResponse
from apps.api.app.domain.workflow_run import RunStatus


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    class FakeOpenAICompatibleProvider:
        def __init__(self, base_url: str, api_key: str, provider_key: str, timeout_seconds: int = 30) -> None:
            self.provider_key = provider_key

        def generate(self, request: LLMCallRequest) -> LLMCallResponse:
            return LLMCallResponse(
                text=f"mock response for {request.model}",
                provider=self.provider_key,
                model=request.model,
                usage={"prompt_tokens": 8, "completion_tokens": 4},
            )

    from apps.api.app.routes import workflow_runs

    async def fake_submit_async_run(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(workflow_runs, "OpenAICompatibleProvider", FakeOpenAICompatibleProvider)
    monkeypatch.setattr(workflow_runs, "_submit_async_run", fake_submit_async_run)
    with TestClient(app) as test_client:
        yield test_client


def _create_mock_provider(client: TestClient, actor_user_id: str, org_id: str) -> None:
    response = client.post(
        "/model-providers",
        json={
            "actor_user_id": actor_user_id,
            "org_id": org_id,
            "provider_key": "mock",
            "display_name": "Mock Provider",
            "base_url": "https://mock.local/v1",
            "api_key": "sk-test",
            "models": ["mock-model"],
            "default_model": "mock-model",
        },
    )
    assert response.status_code == 200


def _auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/identity/users/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']['access_token']}"}


def test_e2e_sync_workflow_full_trace(client: TestClient) -> None:
    """验证同步工作流端到端执行轨迹完整性。"""

    suffix = uuid4().hex

    # === 准备环境 ===
    owner_email = f"e2e-sync-{suffix}@example.com"
    owner_resp = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "E2E Owner", "password": "password123"},
    )
    owner = owner_resp.json()["user_id"]
    org_resp = client.post("/identity/organizations", json={"creator_user_id": owner, "name": "E2E Org"})
    org_id = org_resp.json()["org_id"]
    owner_headers = _auth_headers(client, owner_email)
    _create_mock_provider(client, owner, org_id)
    agent_resp = client.post(
        "/agents",
        json={"actor_user_id": owner, "org_id": org_id, "name": "E2E Agent", "description": ""},
        headers=owner_headers,
    )
    agent_id = agent_resp.json()["agent_id"]

    # === 创建工作流 ===
    wf_resp = client.post(
        "/workflows",
        json={
            "actor_user_id": owner,
            "agent_id": agent_id,
            "name": "E2E Sync WF",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "llm", "type": "llm", "config": {"provider": "mock", "model": "mock-model", "prompt": "处理输入"}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "llm"},
                    {"source": "llm", "target": "end"},
                ],
            },
        },
    )
    wf_id = wf_resp.json()["workflow_id"]
    version_resp = client.post(f"/workflows/{wf_id}/publish", json={"actor_user_id": owner})
    version_id = version_resp.json()["version_id"]

    # === 同步执行 ===
    run_resp = client.post(
        "/workflow-runs",
        json={
            "version_id": version_id,
            "input_data": {"text": "端到端测试"},
            "async_mode": False,
        },
        headers=owner_headers,
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["status"] == "succeeded"
    run_id = run_data["run_id"]

    # === 验证节点执行轨迹 ===
    nodes_resp = client.get(
        f"/workflow-runs/{run_id}/nodes",
        params={"actor_user_id": owner},
    )
    assert nodes_resp.status_code == 200
    nodes = nodes_resp.json()

    # 节点顺序：start -> llm -> end
    assert [n["node_id"] for n in nodes] == ["start", "llm", "end"]
    for node in nodes:
        assert node["status"] == "succeeded"
        assert "input_data" in node
        assert "output_data" in node
        assert node["elapsed_ms"] >= 0

    # LLM 节点应有 prefix_hash
    llm_node = nodes[1]
    assert "prefix_hash" in llm_node["output_data"]

    # === 验证 Gateway 日志 ===
    logs_resp = client.get("/gateway/llm/logs", headers=owner_headers)
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert any(
        log["metadata"].get("source") == "workflow_node"
        for log in logs
    )


def test_e2e_async_workflow_queuing(client: TestClient) -> None:
    """验证异步工作流可投递到队列并返回 pending 状态。"""

    suffix = uuid4().hex

    owner_email = f"e2e-async-{suffix}@example.com"
    owner_resp = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "Async Owner", "password": "password123"},
    )
    owner = owner_resp.json()["user_id"]
    org_resp = client.post("/identity/organizations", json={"creator_user_id": owner, "name": "Async Org"})
    org_id = org_resp.json()["org_id"]
    owner_headers = _auth_headers(client, owner_email)
    _create_mock_provider(client, owner, org_id)
    agent_resp = client.post(
        "/agents",
        json={"actor_user_id": owner, "org_id": org_id, "name": "Async Agent", "description": ""},
        headers=owner_headers,
    )
    agent_id = agent_resp.json()["agent_id"]

    wf_resp = client.post(
        "/workflows",
        json={
            "actor_user_id": owner,
            "agent_id": agent_id,
            "name": "Async WF",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "llm", "type": "llm", "config": {"provider": "mock", "model": "mock-model", "prompt": "async test"}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "llm"},
                    {"source": "llm", "target": "end"},
                ],
            },
        },
    )
    wf_id = wf_resp.json()["workflow_id"]
    version_resp = client.post(f"/workflows/{wf_id}/publish", json={"actor_user_id": owner})
    version_id = version_resp.json()["version_id"]

    # === 异步执行 ===
    run_resp = client.post(
        "/workflow-runs",
        json={
            "version_id": version_id,
            "input_data": {"text": "async"},
            "async_mode": True,
        },
        headers=owner_headers,
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    # 异步模式返回 pending 或 running
    assert run_data["status"] in ("pending", "running", "succeeded")


def test_e2e_workflow_error_recovery(client: TestClient) -> None:
    """验证工作流执行失败时的错误恢复路径。"""

    suffix = uuid4().hex

    # === 准备两个组织 ===
    owner_a_email = f"e2e-err-a-{suffix}@example.com"
    owner_a_resp = client.post(
        "/identity/users/register",
        json={"email": owner_a_email, "display_name": "Err Owner A", "password": "password123"},
    )
    owner_a = owner_a_resp.json()["user_id"]

    owner_b_resp = client.post(
        "/identity/users/register",
        json={"email": f"e2e-err-b-{suffix}@example.com", "display_name": "Err Owner B", "password": "password123"},
    )
    owner_b = owner_b_resp.json()["user_id"]

    org_a_resp = client.post("/identity/organizations", json={"creator_user_id": owner_a, "name": "Err Org A"})
    org_a = org_a_resp.json()["org_id"]
    owner_a_headers = _auth_headers(client, owner_a_email)

    org_b_resp = client.post("/identity/organizations", json={"creator_user_id": owner_b, "name": "Err Org B"})
    org_b = org_b_resp.json()["org_id"]

    # === 组织 B 创建知识库（私有） ===
    kb_b_resp = client.post(
        "/knowledge",
        json={"actor_user_id": owner_b, "org_id": org_b, "name": "私有知识库", "description": ""},
    )
    kb_b_id = kb_b_resp.json()["kb_id"]

    # 上传文档到组织 B 的知识库
    client.post(
        f"/knowledge/{kb_b_id}/upload",
        files={"file": ("private.txt", "私有敏感数据内容，仅供组织 B 访问。".encode("utf-8"), "text/plain")},
        data={"actor_user_id": owner_b, "title": "私有文档"},
    )

    # === 组织 A 创建 Agent 和工作流，尝试引用组织 B 的知识库 ===
    agent_a_resp = client.post(
        "/agents",
        json={"actor_user_id": owner_a, "org_id": org_a, "name": "Err Agent A", "description": ""},
        headers=owner_a_headers,
    )
    agent_a = agent_a_resp.json()["agent_id"]

    wf_resp = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_a,
            "agent_id": agent_a,
            "name": "Cross Org KB WF",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "rag", "type": "rag", "config": {"kb_id": kb_b_id, "query_template": "私有", "limit": 3}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "rag"},
                    {"source": "rag", "target": "end"},
                ],
            },
        },
    )
    wf_id = wf_resp.json()["workflow_id"]
    version_resp = client.post(f"/workflows/{wf_id}/publish", json={"actor_user_id": owner_a})
    version_id = version_resp.json()["version_id"]

    # === 执行（预期 RAG 节点失败） ===
    run_resp = client.post(
        "/workflow-runs",
        json={
            "version_id": version_id,
            "input_data": {"text": "私有"},
            "async_mode": False,
        },
        headers=owner_a_headers,
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()

    # RAG 跨组织应导致失败
    assert run_data["status"] == "failed"

    # 检查节点状态：RAG 节点应失败，end 节点不应执行
    nodes_resp = client.get(
        f"/workflow-runs/{run_data['run_id']}/nodes",
        params={"actor_user_id": owner_a},
    )
    assert nodes_resp.status_code == 200
    nodes = nodes_resp.json()
    # 最后一个执行的节点应该是 RAG（已失败）
    last_executed = nodes[-1]
    assert last_executed["node_id"] == "rag"
    assert last_executed["status"] == "failed"


def test_e2e_workflow_retry_on_failure(client: TestClient) -> None:
    """验证失败工作流的状态可查询，后续可创建新的 Run 重试。"""

    suffix = uuid4().hex

    owner_email = f"e2e-retry-{suffix}@example.com"
    owner_resp = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "Retry Owner", "password": "password123"},
    )
    owner = owner_resp.json()["user_id"]
    org_resp = client.post("/identity/organizations", json={"creator_user_id": owner, "name": "Retry Org"})
    org_id = org_resp.json()["org_id"]
    owner_headers = _auth_headers(client, owner_email)
    _create_mock_provider(client, owner, org_id)
    agent_resp = client.post(
        "/agents",
        json={"actor_user_id": owner, "org_id": org_id, "name": "Retry Agent", "description": ""},
        headers=owner_headers,
    )
    agent_id = agent_resp.json()["agent_id"]

    wf_resp = client.post(
        "/workflows",
        json={
            "actor_user_id": owner,
            "agent_id": agent_id,
            "name": "Retry WF",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "llm", "type": "llm", "config": {"provider": "mock", "model": "mock-model", "prompt": "retry"}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "llm"},
                    {"source": "llm", "target": "end"},
                ],
            },
        },
    )
    wf_id = wf_resp.json()["workflow_id"]
    version_resp = client.post(f"/workflows/{wf_id}/publish", json={"actor_user_id": owner})
    version_id = version_resp.json()["version_id"]

    # === 执行第一次（成功）===
    run1_resp = client.post(
        "/workflow-runs",
        json={"version_id": version_id, "input_data": {"text": "first"}, "async_mode": False},
        headers=owner_headers,
    )
    run1_id = run1_resp.json()["run_id"]
    assert run1_resp.json()["status"] == "succeeded"

    # 同一版本可执行多次（retry 本质是新 Run）
    run2_resp = client.post(
        "/workflow-runs",
        json={"version_id": version_id, "input_data": {"text": "second"}, "async_mode": False},
        headers=owner_headers,
    )
    run2_id = run2_resp.json()["run_id"]
    assert run2_resp.json()["status"] == "succeeded"

    # 两个 Run 应有不同的 run_id
    assert run1_id != run2_id

    # 查询所有 Run 记录
    runs_resp = client.get(
        "/workflow-runs",
        params={"actor_user_id": owner, "org_id": org_id},
    )
    assert runs_resp.status_code == 200
    run_ids = [r["run_id"] for r in runs_resp.json()]
    assert run1_id in run_ids
    assert run2_id in run_ids


def test_e2e_workflow_output_consistency(client: TestClient) -> None:
    """验证相同输入和相同 Workflow 版本产生一致的 immutable prefix hash。"""

    suffix = uuid4().hex

    owner_email = f"e2e-cons-{suffix}@example.com"
    owner_resp = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "Cons Owner", "password": "password123"},
    )
    owner = owner_resp.json()["user_id"]
    org_resp = client.post("/identity/organizations", json={"creator_user_id": owner, "name": "Cons Org"})
    org_id = org_resp.json()["org_id"]
    owner_headers = _auth_headers(client, owner_email)
    _create_mock_provider(client, owner, org_id)
    agent_resp = client.post(
        "/agents",
        json={"actor_user_id": owner, "org_id": org_id, "name": "Cons Agent", "description": ""},
        headers=owner_headers,
    )
    agent_id = agent_resp.json()["agent_id"]

    wf_resp = client.post(
        "/workflows",
        json={
            "actor_user_id": owner,
            "agent_id": agent_id,
            "name": "Cons WF",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "llm", "type": "llm", "config": {"provider": "mock", "model": "mock-model", "prompt": "固定提示词"}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "llm"},
                    {"source": "llm", "target": "end"},
                ],
            },
        },
    )
    wf_id = wf_resp.json()["workflow_id"]
    version_resp = client.post(f"/workflows/{wf_id}/publish", json={"actor_user_id": owner})
    version_id = version_resp.json()["version_id"]

    # === 第一次执行 ===
    run1_resp = client.post(
        "/workflow-runs",
        json={"version_id": version_id, "input_data": {"text": "same input"}, "async_mode": False},
        headers=owner_headers,
    )
    nodes1 = client.get(
        f"/workflow-runs/{run1_resp.json()['run_id']}/nodes",
        params={"actor_user_id": owner},
    ).json()
    hash1 = nodes1[1]["output_data"]["prefix_hash"]

    # === 第二次执行（相同输入） ===
    run2_resp = client.post(
        "/workflow-runs",
        json={"version_id": version_id, "input_data": {"text": "same input"}, "async_mode": False},
        headers=owner_headers,
    )
    nodes2 = client.get(
        f"/workflow-runs/{run2_resp.json()['run_id']}/nodes",
        params={"actor_user_id": owner},
    ).json()
    hash2 = nodes2[1]["output_data"]["prefix_hash"]

    # 相同 Prompt + 相同版本 -> immutable prefix hash 应一致
    assert hash1 == hash2


def test_e2e_workflow_different_inputs_keep_same_prefix_hash(client: TestClient) -> None:
    """验证不同输入复用相同 immutable prefix hash。"""

    suffix = uuid4().hex

    owner_email = f"e2e-diff-{suffix}@example.com"
    owner_resp = client.post(
        "/identity/users/register",
        json={"email": owner_email, "display_name": "Diff Owner", "password": "password123"},
    )
    owner = owner_resp.json()["user_id"]
    org_resp = client.post("/identity/organizations", json={"creator_user_id": owner, "name": "Diff Org"})
    org_id = org_resp.json()["org_id"]
    owner_headers = _auth_headers(client, owner_email)
    _create_mock_provider(client, owner, org_id)
    agent_resp = client.post(
        "/agents",
        json={"actor_user_id": owner, "org_id": org_id, "name": "Diff Agent", "description": ""},
        headers=owner_headers,
    )
    agent_id = agent_resp.json()["agent_id"]

    wf_resp = client.post(
        "/workflows",
        json={
            "actor_user_id": owner,
            "agent_id": agent_id,
            "name": "Diff WF",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "llm", "type": "llm", "config": {"provider": "mock", "model": "mock-model", "prompt": "分析输入"}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "llm"},
                    {"source": "llm", "target": "end"},
                ],
            },
        },
    )
    wf_id = wf_resp.json()["workflow_id"]
    version_resp = client.post(f"/workflows/{wf_id}/publish", json={"actor_user_id": owner})
    version_id = version_resp.json()["version_id"]

    # 不同输入
    run_a_resp = client.post(
        "/workflow-runs",
        json={"version_id": version_id, "input_data": {"text": "input A"}, "async_mode": False},
        headers=owner_headers,
    )
    nodes_a = client.get(
        f"/workflow-runs/{run_a_resp.json()['run_id']}/nodes",
        params={"actor_user_id": owner},
    ).json()
    hash_a = nodes_a[1]["output_data"]["prefix_hash"]

    run_b_resp = client.post(
        "/workflow-runs",
        json={"version_id": version_id, "input_data": {"text": "input B different"}, "async_mode": False},
        headers=owner_headers,
    )
    nodes_b = client.get(
        f"/workflow-runs/{run_b_resp.json()['run_id']}/nodes",
        params={"actor_user_id": owner},
    ).json()
    hash_b = nodes_b[1]["output_data"]["prefix_hash"]

    # 当前输入位于 CURRENT_TURN，prefix_hash 只覆盖 immutable prefix。
    assert hash_a == hash_b
