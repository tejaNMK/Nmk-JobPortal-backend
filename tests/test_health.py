from fastapi.testclient import TestClient

from app.config import get_db
from app.main import init_app


class HealthySession:
    async def execute(self, *args, **kwargs):
        return None


class UnavailableSession:
    async def execute(self, *args, **kwargs):
        raise RuntimeError(
            "database unavailable: postgresql+asyncpg://user:password@host/db"
        )


def _client_with_session(session):
    app = init_app()

    async def fake_db():
        yield session

    app.dependency_overrides[get_db] = fake_db
    return TestClient(app, raise_server_exceptions=False)


def test_health_returns_200_when_app_and_database_are_healthy():
    client = _client_with_session(HealthySession())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "database": "connected",
    }


def test_health_returns_503_when_database_is_unavailable():
    client = _client_with_session(UnavailableSession())

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "database": "disconnected",
    }
    assert "password" not in response.text
    assert "postgresql+asyncpg" not in response.text


def test_health_does_not_require_authentication():
    client = _client_with_session(HealthySession())

    response = client.get("/health")

    assert response.status_code == 200


def test_health_response_structure_is_documented_without_bearer_auth():
    app = init_app()
    schema = app.openapi()

    assert schema["paths"]["/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/HealthCheckResponse")
    assert "security" not in schema["paths"]["/health"]["get"]
