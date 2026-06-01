"""API 健康检查测试。"""

from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_health_check_returns_ok() -> None:
    """健康检查应返回 API 服务可用状态。"""

    # client 是 FastAPI 测试客户端，用于不启动真实网络服务时调用接口。
    client = TestClient(app)

    # response 是健康检查接口响应。
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}
