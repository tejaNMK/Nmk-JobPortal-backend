import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import cors
from app import config


PRODUCTION_ORIGIN = "https://production-frontend-domain.com"
MALICIOUS_ORIGIN = "https://evil.example"
LOCALHOST_ORIGIN = "http://localhost:3000"


def _client_with_cors(monkeypatch, origins, *, allow_credentials=False):
    monkeypatch.setattr(cors, "CORS_ALLOWED_ORIGINS", origins)
    monkeypatch.setattr(cors, "CORS_ALLOW_CREDENTIALS", allow_credentials)
    monkeypatch.setattr(
        cors,
        "CORS_ALLOWED_METHODS",
        ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    monkeypatch.setattr(
        cors,
        "CORS_ALLOWED_HEADERS",
        ["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    )

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/auth/login")
    def login():
        return {"status": "ok"}

    cors.configure_cors(app)
    return TestClient(app)


def test_production_frontend_origin_is_allowed(monkeypatch):
    client = _client_with_cors(monkeypatch, [PRODUCTION_ORIGIN])

    response = client.get(
        "/health",
        headers={"Origin": PRODUCTION_ORIGIN},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == PRODUCTION_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_unknown_origin_is_rejected(monkeypatch):
    client = _client_with_cors(monkeypatch, [PRODUCTION_ORIGIN])

    response = client.get(
        "/health",
        headers={"Origin": MALICIOUS_ORIGIN},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_preflight_options_request_works_for_trusted_origin(monkeypatch):
    client = _client_with_cors(monkeypatch, [PRODUCTION_ORIGIN])

    response = client.options(
        "/auth/login",
        headers={
            "Origin": PRODUCTION_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == PRODUCTION_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "Authorization" in response.headers["access-control-allow-headers"]
    assert "Content-Type" in response.headers["access-control-allow-headers"]


def test_localhost_origin_is_allowed_in_development_when_configured():
    origins = config.validate_cors_origins(
        [LOCALHOST_ORIGIN],
        app_env="development",
        allow_credentials=False,
    )

    assert origins == [LOCALHOST_ORIGIN]


def test_localhost_origin_is_rejected_in_production():
    with pytest.raises(RuntimeError, match="Localhost CORS origins"):
        config.validate_cors_origins(
            [LOCALHOST_ORIGIN],
            app_env="production",
            allow_credentials=False,
        )


def test_wildcard_origin_is_rejected():
    with pytest.raises(RuntimeError, match="wildcard"):
        config.validate_cors_origins(
            ["*"],
            app_env="production",
            allow_credentials=True,
        )


def test_development_defaults_are_not_enabled_in_production(monkeypatch):
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
        config.get_cors_allowed_origins("production", allow_credentials=False)

    assert config.get_cors_allowed_origins(
        "development",
        allow_credentials=False,
    ) == list(config.DEV_DEFAULT_CORS_ORIGINS)
