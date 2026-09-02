from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.dependencies.auth_dependencies import (
    SESSION_EXPIRED_DETAIL,
    get_jwt_payload_401,
)
from app.schema.auth import ChangePasswordSchema
from app.service.authentication.auth_service import AuthService


class FakeSession:
    pass


def _request(token: str = "token"):
    return SimpleNamespace(headers={"Authorization": f"Bearer {token}"})


def _active_user():
    return SimpleNamespace(
        user_id="user-1",
        first_name="Test",
        last_name="User",
        email="user@example.com",
        password_hash="old-hash",
        deleted_flag=False,
        user_status="ACTIVE",
    )


@pytest.mark.asyncio
async def test_auth_dependency_rejects_token_without_session_jti(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.JWTRepo.extract_token",
        lambda token: {"user_id": "user-1"},
    )

    with pytest.raises(HTTPException) as exc:
        await get_jwt_payload_401(_request(), FakeSession())

    assert exc.value.status_code == 401
    assert exc.value.detail == SESSION_EXPIRED_DETAIL


@pytest.mark.asyncio
async def test_auth_dependency_rejects_revoked_session(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.JWTRepo.extract_token",
        lambda token: {"user_id": "user-1", "jti": "old-session"},
    )
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.UserSessionRepository.find_active_session_by_jwt_id",
        AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exc:
        await get_jwt_payload_401(_request(), FakeSession())

    assert exc.value.status_code == 401
    assert exc.value.detail == SESSION_EXPIRED_DETAIL


@pytest.mark.asyncio
async def test_auth_dependency_allows_active_session_for_active_user(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.JWTRepo.extract_token",
        lambda token: {"user_id": "user-1", "jti": "live-session"},
    )
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.UserSessionRepository.find_active_session_by_jwt_id",
        AsyncMock(return_value=SimpleNamespace(user_id="user-1")),
    )
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.UsersRepository.find_by_user_id",
        AsyncMock(return_value=_active_user()),
    )

    payload = await get_jwt_payload_401(_request(), FakeSession())

    assert payload["user_id"] == "user-1"


@pytest.mark.asyncio
async def test_auth_dependency_rejects_inactive_user(monkeypatch):
    user = _active_user()
    user.user_status = "INACTIVE"
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.JWTRepo.extract_token",
        lambda token: {"user_id": "user-1", "jti": "live-session"},
    )
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.UserSessionRepository.find_active_session_by_jwt_id",
        AsyncMock(return_value=SimpleNamespace(user_id="user-1")),
    )
    monkeypatch.setattr(
        "app.dependencies.auth_dependencies.UsersRepository.find_by_user_id",
        AsyncMock(return_value=user),
    )

    with pytest.raises(HTTPException) as exc:
        await get_jwt_payload_401(_request(), FakeSession())

    assert exc.value.status_code == 401
    assert exc.value.detail == SESSION_EXPIRED_DETAIL


@pytest.mark.asyncio
async def test_change_password_sign_out_everywhere_revokes_all_sessions(monkeypatch):
    user = _active_user()
    logout_all = AsyncMock(return_value=3)
    monkeypatch.setattr(
        "app.service.authentication.auth_service.UsersRepository.find_by_user_id",
        AsyncMock(return_value=user),
    )
    monkeypatch.setattr(
        "app.service.authentication.auth_service.UsersRepository.update_password",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.service.authentication.auth_service.UserSessionRepository.logout_all_sessions",
        logout_all,
    )
    monkeypatch.setattr(
        "app.service.authentication.auth_service.ActivityLogService.create_log",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.service.authentication.auth_service.ActivityLogService.create_log_for_user_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.service.authentication.auth_service.pwd_context.verify",
        lambda password, password_hash: password == "CurrentA1!",
    )
    monkeypatch.setattr(
        "app.service.authentication.auth_service.pwd_context.hash",
        lambda password: "new-hash",
    )

    result = await AuthService.change_password_service(
        session=FakeSession(),
        user_id="user-1",
        change_password=ChangePasswordSchema(
            current_password="CurrentA1!",
            new_password="NewPassA1!",
            confirm_password="NewPassA1!",
            sign_out_everywhere=True,
        ),
    )

    logout_all.assert_awaited_once()
    assert isinstance(logout_all.await_args.kwargs["session"], FakeSession)
    assert logout_all.await_args.kwargs["user_id"] == "user-1"
    assert result["sessions_terminated"] == 3
