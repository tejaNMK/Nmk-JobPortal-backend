import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app
from app.security import rate_limiter
from app.security.rate_limiter import (
    AuthRateLimiter,
    CHANGE_PASSWORD_RULES,
    LOGIN_RULES,
    SEND_EMAIL_OTP_RULES,
    SUPER_ADMIN_LOGIN_RULES,
    VERIFY_EMAIL_OTP_RULES,
    get_client_ip,
    hash_identifier,
    normalize_email,
    normalize_phone,
)


async def fake_db():
    yield SimpleNamespace()


def make_app_with_memory_limiter():
    app = init_app()
    app.dependency_overrides[get_db] = fake_db
    rate_limiter.auth_rate_limiter = AuthRateLimiter()
    rate_limiter.auth_rate_limiter.reset()
    return app


@pytest.fixture(autouse=True)
def memory_rate_limiter(monkeypatch):
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_STORAGE_URL", "memory://")
    rate_limiter.auth_rate_limiter = AuthRateLimiter()
    yield
    rate_limiter.auth_rate_limiter.reset()


def post_login(client, email="john.doe@example.com"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": "SecurePass123!"},
    )


def assert_429(response):
    assert response.status_code == 429
    assert response.headers.get("Retry-After")
    body = response.json()
    assert body["success"] is False
    assert body["status"] == 429
    assert body["message"] == "Too many requests. Please try again later."
    assert body["error"]["code"] == "TOO_MANY_REQUESTS"
    assert "john.doe@example.com" not in str(body)
    assert "+14155552671" not in str(body)


def test_request_below_limit_succeeds():
    app = make_app_with_memory_limiter()
    client = TestClient(app)

    with patch(
        "app.middleware.maintenance_mode.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.controller.authentication.authentication.AuthService.login_service",
        new_callable=AsyncMock,
        return_value={"access_token": "jwt-token", "token_type": "bearer"},
    ), patch(
        "app.controller.authentication.authentication.AuthService.authenticate_user",
        new_callable=AsyncMock,
        return_value={"user_id": "1", "email": "john.doe@example.com", "roles": []},
    ):
        response = post_login(client)

    assert response.status_code == 200


def test_exceeding_limit_returns_429_and_retry_after():
    app = make_app_with_memory_limiter()
    client = TestClient(app)

    with patch(
        "app.middleware.maintenance_mode.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.controller.authentication.authentication.AuthService.login_service",
        new_callable=AsyncMock,
        return_value={"access_token": "jwt-token", "token_type": "bearer"},
    ), patch(
        "app.controller.authentication.authentication.AuthService.authenticate_user",
        new_callable=AsyncMock,
        return_value={"user_id": "1", "email": "john.doe@example.com", "roles": []},
    ):
        for _ in range(5):
            assert post_login(client).status_code == 200
        response = post_login(client)

    assert_429(response)


@pytest.mark.asyncio
async def test_rate_limit_window_resets(monkeypatch):
    limiter = AuthRateLimiter()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [],
            "client": ("203.0.113.10", 12345),
        }
    )
    body = {"email": "john.doe@example.com"}

    now = 1000.0
    monkeypatch.setattr(rate_limiter.time, "time", lambda: now)
    for _ in range(5):
        await limiter.check(request, body, LOGIN_RULES)

    with pytest.raises(Exception) as exc:
        await limiter.check(request, body, LOGIN_RULES)
    assert getattr(exc.value, "status_code", None) == 429

    now = 1061.0
    await limiter.check(request, body, LOGIN_RULES)


def test_repeated_login_attempts_are_blocked_before_service():
    app = make_app_with_memory_limiter()
    client = TestClient(app)

    with patch(
        "app.middleware.maintenance_mode.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.controller.authentication.authentication.AuthService.login_service",
        new_callable=AsyncMock,
        return_value={"access_token": "jwt-token", "token_type": "bearer"},
    ) as login_service, patch(
        "app.controller.authentication.authentication.AuthService.authenticate_user",
        new_callable=AsyncMock,
        return_value={"user_id": "1", "email": "john.doe@example.com", "roles": []},
    ):
        for _ in range(5):
            post_login(client)
        response = post_login(client)

    assert response.status_code == 429
    assert login_service.await_count == 5


@pytest.mark.asyncio
async def test_different_users_same_ip_not_blocked_by_identifier_limit_only():
    limiter = AuthRateLimiter()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [],
            "client": ("203.0.113.11", 12345),
        }
    )

    for index in range(5):
        await limiter.check(
            request,
            {"email": f"user{index}@example.com"},
            LOGIN_RULES,
        )


@pytest.mark.asyncio
async def test_ip_level_protection_prevents_password_spraying():
    limiter = AuthRateLimiter()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [],
            "client": ("203.0.113.12", 12345),
        }
    )

    for index in range(5):
        await limiter.check(
            request,
            {"email": f"spray{index}@example.com"},
            LOGIN_RULES,
        )

    with pytest.raises(Exception) as exc:
        await limiter.check(request, {"email": "spray5@example.com"}, LOGIN_RULES)
    assert getattr(exc.value, "status_code", None) == 429


def test_email_and_phone_normalization_and_hashing():
    assert normalize_email("  John.Doe@Example.COM ") == "john.doe@example.com"
    assert normalize_phone(" +1 (415) 555-2671 ") == "+14155552671"
    assert "john.doe@example.com" not in hash_identifier("john.doe@example.com")


def test_otp_send_flooding_is_blocked():
    app = make_app_with_memory_limiter()
    client = TestClient(app)

    with patch(
        "app.middleware.maintenance_mode.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.controller.authentication.authentication.AuthService.send_otp_service",
        new_callable=AsyncMock,
        return_value={"message": "OTP sent successfully"},
    ) as service:
        for _ in range(3):
            assert client.post("/auth/send-otp", json={"email": "JOHN.DOE@example.com"}).status_code == 200
        response = client.post("/auth/send-otp", json={"email": "john.doe@example.com"})

    assert response.status_code == 429
    assert service.await_count == 3


@pytest.mark.asyncio
async def test_otp_verification_brute_force_is_blocked():
    limiter = AuthRateLimiter()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/verify-otp",
            "headers": [],
            "client": ("203.0.113.13", 12345),
        }
    )
    body = {"email": "john.doe@example.com", "otp_code": "123456"}

    for _ in range(5):
        await limiter.check(request, body, VERIFY_EMAIL_OTP_RULES)

    with pytest.raises(Exception) as exc:
        await limiter.check(request, body, VERIFY_EMAIL_OTP_RULES)
    assert getattr(exc.value, "status_code", None) == 429


def test_super_admin_stricter_login_limit():
    app = make_app_with_memory_limiter()
    client = TestClient(app)

    with patch(
        "app.middleware.maintenance_mode.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.controller.super_admin.auth.SuperAdminAuthService.login",
        new_callable=AsyncMock,
        return_value={"access_token": "jwt-token", "token_type": "bearer"},
    ) as service:
        for _ in range(3):
            response = client.post(
                "/super-admin/login",
                json={"email": "admin@example.com", "password": "SecurePass123!"},
            )
            assert response.status_code == 200
        response = client.post(
            "/super-admin/login",
            json={"email": "admin@example.com", "password": "SecurePass123!"},
        )

    assert response.status_code == 429
    assert service.await_count == 3


def test_spoofed_forwarded_for_from_untrusted_source_is_ignored(monkeypatch):
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_TRUSTED_PROXY_IPS", ["127.0.0.1"])
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [(b"x-forwarded-for", b"198.51.100.10")],
            "client": ("203.0.113.200", 12345),
        }
    )

    assert get_client_ip(request) == "203.0.113.200"


def test_trusted_proxy_header_works(monkeypatch):
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_TRUSTED_PROXY_IPS", ["127.0.0.1"])
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [(b"x-forwarded-for", b"198.51.100.10, 127.0.0.1")],
            "client": ("127.0.0.1", 12345),
        }
    )

    assert get_client_ip(request) == "198.51.100.10"


def test_cidr_trusted_proxy_matching(monkeypatch):
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_TRUSTED_PROXY_IPS", ["10.0.0.0/8"])
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [(b"x-forwarded-for", b"198.51.100.20")],
            "client": ("10.20.30.40", 12345),
        }
    )

    assert get_client_ip(request) == "198.51.100.20"


def test_rate_limit_response_does_not_expose_account_existence():
    app = make_app_with_memory_limiter()
    client = TestClient(app)

    with patch(
        "app.middleware.maintenance_mode.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.controller.authentication.authentication.AuthService.send_otp_service",
        new_callable=AsyncMock,
        return_value={"message": "OTP sent successfully"},
    ):
        for _ in range(3):
            client.post("/auth/send-otp", json={"email": "missing@example.com"})
        response = client.post("/auth/send-otp", json={"email": "missing@example.com"})

    assert response.status_code == 429
    assert "missing@example.com" not in str(response.json())


def test_change_password_user_key_limit(monkeypatch):
    app = make_app_with_memory_limiter()

    async def fake_payload(request: Request):
        request.state.jwt_payload = {"user_id": "user-123", "jti": "session-123"}
        return request.state.jwt_payload

    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    client = TestClient(app)

    with patch(
        "app.middleware.maintenance_mode.SystemSettingsRepository.get_active",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.controller.authentication.authentication.AuthService.change_password_service",
        new_callable=AsyncMock,
        return_value={"message": "Password changed successfully"},
    ) as service:
        for _ in range(5):
            response = client.post(
                "/auth/change-password",
                json={
                    "current_password": "CurrPass123!",
                    "new_password": "NewPassA1!234",
                    "confirm_password": "NewPassA1!234",
                },
                headers={"Authorization": "Bearer jwt-token"},
            )
            assert response.status_code == 200
        response = client.post(
            "/auth/change-password",
            json={
                "current_password": "CurrPass123!",
                "new_password": "NewPassA1!234",
                "confirm_password": "NewPassA1!234",
            },
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 429
    assert service.await_count == 5


def test_production_rejects_in_memory_storage(monkeypatch):
    import app.config as config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URL", "memory://")

    with pytest.raises(RuntimeError, match="Redis-backed storage"):
        importlib.reload(config)

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URL", "memory://")
    importlib.reload(config)
