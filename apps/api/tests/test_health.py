"""API 健康检查测试。"""

from app.database import DATABASE_URL, async_engine
from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_api_routes_use_a_file_backed_sqlite_test_database() -> None:
    """Real route dependencies must never fall back to localhost MySQL in tests."""

    assert async_engine.dialect.name == "sqlite"
    assert ":memory:" not in DATABASE_URL


def test_health_check_returns_ok() -> None:
    """健康检查应返回 API 服务可用状态。"""

    # client 是 FastAPI 测试客户端，用于不启动真实网络服务时调用接口。
    client = TestClient(app)

    # response 是健康检查接口响应。
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_testclient_lifespan_keeps_real_route_dependencies_on_sqlite() -> None:
    """Startup plus a DB-backed route must stay on the configured test engine."""

    with TestClient(app) as client:
        response = client.post(
            "/identity/users/register",
            json={
                "email": "sqlite-lifespan@example.com",
                "display_name": "SQLite lifespan",
                "password": "password123",
            },
        )

    assert response.status_code == 200
