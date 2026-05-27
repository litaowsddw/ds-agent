"""知识库 API 集成测试。"""

from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_knowledge_api_create_and_search() -> None:
    """创建知识库、上传文档、检索 Chunk 的 API 主链路。"""
    client = TestClient(app)

    # 注册用户和组织
    reg = client.post(
        "/identity/users/register",
        json={
            "email": "kb_api@test.com",
            "display_name": "KB",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    uid = reg.json()["user_id"]

    org = client.post(
        "/identity/organizations",
        json={"creator_user_id": uid, "name": "KB Org"},
    )
    assert org.status_code == 200
    oid = org.json()["org_id"]

    # 创建知识库
    kb = client.post(
        "/knowledge",
        json={
            "actor_user_id": uid,
            "org_id": oid,
            "name": "API KB",
            "description": "test",
        },
    )
    assert kb.status_code == 200
    kb_id = kb.json()["kb_id"]

    # 上传文档
    doc = client.post(
        f"/knowledge/{kb_id}/documents",
        json={
            "actor_user_id": uid,
            "title": "API Doc",
            "content": "FastAPI 是高性能 Python Web 框架",
            "chunk_size": 20,
        },
    )
    assert doc.status_code == 200
    assert doc.json()["status"] == "indexed"

    # 检索
    search = client.post(
        f"/knowledge/{kb_id}/search",
        json={
            "actor_user_id": uid,
            "query": "FastAPI",
            "limit": 3,
        },
    )
    assert search.status_code == 200
    assert len(search.json()) > 0
