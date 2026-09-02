from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import SentrySettings, get_sentry_settings
from app.exception_handlers import register_exception_handlers
from app.main import init_app
from app.observability import sentry as sentry_module


class Payload(BaseModel):
    name: str


def _build_error_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/unauthorized")
    async def unauthorized():
        raise HTTPException(status_code=401, detail="Missing token")

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="Access denied")

    @app.get("/conflict")
    async def conflict():
        raise HTTPException(status_code=409, detail="Already exists")

    @app.post("/validate")
    async def validate(payload: Payload):
        return payload.model_dump()

    return app


def test_sentry_disabled_when_dsn_is_missing(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    with patch.object(sentry_module.sentry_sdk, "init") as init:
        enabled = sentry_module.initialize_sentry()

    assert enabled is False
    init.assert_not_called()


def test_application_starts_when_sentry_dsn_is_missing(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    with patch.object(sentry_module.sentry_sdk, "init") as init:
        app = init_app()

    assert isinstance(app, FastAPI)
    init.assert_not_called()


def test_application_starts_when_sentry_dsn_is_empty(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "")

    with patch.object(sentry_module.sentry_sdk, "init") as init:
        app = init_app()

    assert isinstance(app, FastAPI)
    init.assert_not_called()


def test_sentry_initializes_with_configured_environment_release_and_sample_rate():
    settings = SentrySettings(
        dsn="https://public@example.invalid/1",
        environment="production",
        release="backend@1.2.3",
        traces_sample_rate=0.25,
    )

    with patch.object(sentry_module.sentry_sdk, "init") as init:
        enabled = sentry_module.initialize_sentry(settings)

    assert enabled is True
    init.assert_called_once()
    kwargs = init.call_args.kwargs
    assert kwargs["dsn"] == "https://public@example.invalid/1"
    assert kwargs["environment"] == "production"
    assert kwargs["release"] == "backend@1.2.3"
    assert kwargs["traces_sample_rate"] == 0.25
    assert kwargs["send_default_pii"] is False
    assert kwargs["before_send"] is sentry_module.before_send
    assert {type(integration).__name__ for integration in kwargs["integrations"]} == {
        "FastApiIntegration",
        "StarletteIntegration",
    }


def test_sentry_settings_parse_trace_sample_rate(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "staging")
    monkeypatch.setenv("SENTRY_RELEASE", "backend@abc123")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.75")

    settings = get_sentry_settings()

    assert settings.dsn == "https://public@example.invalid/1"
    assert settings.environment == "staging"
    assert settings.release == "backend@abc123"
    assert settings.traces_sample_rate == 0.75


def test_invalid_trace_sample_rate_is_ignored(monkeypatch):
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "1.5")

    assert get_sentry_settings().traces_sample_rate is None

    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "not-a-float")

    assert get_sentry_settings().traces_sample_rate is None


def test_before_send_redacts_sensitive_fields_and_keeps_harmless_data():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer token-value",
                "Cookie": "session=abc",
                "X-Request-ID": "req-123",
            },
            "data": {
                "password": "secret-password",
                "otp": "123456",
                "access_token": "access",
                "refresh_token": "refresh",
                "profile_name": "Candidate Name",
            },
        },
        "extra": {
            "database_url": "postgresql://user:pass@db/name",
            "safe_count": 3,
        },
    }

    sanitized = sentry_module.before_send(event, {})

    assert sanitized["request"]["headers"]["Authorization"] == sentry_module.REDACTED
    assert sanitized["request"]["headers"]["Cookie"] == sentry_module.REDACTED
    assert sanitized["request"]["data"]["password"] == sentry_module.REDACTED
    assert sanitized["request"]["data"]["otp"] == sentry_module.REDACTED
    assert sanitized["request"]["data"]["access_token"] == sentry_module.REDACTED
    assert sanitized["request"]["data"]["refresh_token"] == sentry_module.REDACTED
    assert sanitized["extra"]["database_url"] == sentry_module.REDACTED
    assert sanitized["request"]["headers"]["X-Request-ID"] == "req-123"
    assert sanitized["request"]["data"]["profile_name"] == "Candidate Name"
    assert sanitized["extra"]["safe_count"] == 3


def test_expected_http_and_validation_errors_keep_existing_response_behavior():
    client = TestClient(_build_error_app())

    unauthorized = client.get("/unauthorized")
    forbidden = client.get("/forbidden")
    missing = client.get("/missing")
    conflict = client.get("/conflict")
    validation = client.post("/validate", json={})

    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "UNAUTHORIZED"
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CONFLICT"
    assert validation.status_code == 422
    assert validation.json()["error"]["code"] == "VALIDATION_ERROR"
