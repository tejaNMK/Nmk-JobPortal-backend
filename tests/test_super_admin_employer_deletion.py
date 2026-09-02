from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.role_dependencies import super_admin_only
from app.main import init_app
from app.service.authentication.auth_service import AuthService
from app.service.super_admin.employer_service import EmployerService


class FakeSession:
    pass


async def fake_db():
    yield FakeSession()


def _app_with_super_admin():
    app = init_app()

    async def fake_super_admin():
        return {"user_id": str(uuid4()), "roles": ["ROLE_SUPER_ADMIN"]}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[super_admin_only] = fake_super_admin
    return app


def test_delete_employer_endpoint_uses_user_uuid(monkeypatch):
    app = _app_with_super_admin()
    user_id = uuid4()
    captured = {}

    async def fake_delete(session, user_id, actor):
        captured["user_id"] = user_id
        captured["actor"] = actor
        return {
            "user_id": str(user_id),
            "employer_profile_id": "employer-profile-1",
            "deletion_type": "soft",
        }

    monkeypatch.setattr(EmployerService, "delete_employer", fake_delete)

    response = TestClient(app).delete(f"/super-admin/employers/{user_id}")

    assert response.status_code == 200
    assert captured["user_id"] == user_id
    assert isinstance(captured["user_id"], UUID)
    assert response.json()["message"] == "Employer account deleted successfully."
    assert response.json()["data"] == {
        "user_id": str(user_id),
        "employer_profile_id": "employer-profile-1",
        "deletion_type": "soft",
    }


def test_delete_employer_endpoint_rejects_malformed_user_uuid(monkeypatch):
    app = _app_with_super_admin()

    async def fake_delete(session, user_id, actor):
        raise AssertionError("Service should not run for malformed UUIDs")

    monkeypatch.setattr(EmployerService, "delete_employer", fake_delete)

    response = TestClient(app).delete("/super-admin/employers/not-a-uuid")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_employer_soft_deletes_by_documented_user_id(monkeypatch):
    user_id = uuid4()
    employer = SimpleNamespace(id="employer-profile-1", company_name="NMK")
    user = SimpleNamespace(
        user_id=user_id,
        first_name="Ravi",
        last_name="Kumar",
        email="ravi@example.com",
    )
    captured = {"log": None, "notification": None}

    async def fake_soft_delete(session, user_id):
        captured["deleted_user_id"] = user_id
        return user, employer

    async def fake_log(**kwargs):
        captured["log"] = kwargs

    async def fake_notification(*args, **kwargs):
        captured["notification"] = kwargs

    monkeypatch.setattr(
        "app.service.super_admin.employer_service."
        "EmployerRepository.soft_delete_employer_by_user_id",
        fake_soft_delete,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.ActivityLogService.create_log",
        fake_log,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.NotificationService.create_for_super_admins",
        fake_notification,
    )

    result = await EmployerService.delete_employer(
        session=FakeSession(),
        user_id=user_id,
        actor={"user_id": str(uuid4()), "roles": ["ROLE_SUPER_ADMIN"]},
    )

    assert captured["deleted_user_id"] == user_id
    assert result == {
        "user_id": str(user_id),
        "employer_profile_id": "employer-profile-1",
        "deletion_type": "soft",
    }
    assert captured["log"]["action"] == "EMPLOYER_DELETED"
    assert captured["log"]["entity_id"] == str(user_id)
    assert captured["log"]["metadata"] == {
        "user_id": str(user_id),
        "employer_profile_id": "employer-profile-1",
        "deletion_type": "soft",
    }
    assert captured["notification"]["entity_id"] == str(user_id)


@pytest.mark.asyncio
async def test_delete_employer_unknown_valid_user_uuid_returns_404(monkeypatch):
    captured = {"logged": False}

    async def fake_soft_delete(session, user_id):
        return None

    async def fake_log(**kwargs):
        captured["logged"] = True

    monkeypatch.setattr(
        "app.service.super_admin.employer_service."
        "EmployerRepository.soft_delete_employer_by_user_id",
        fake_soft_delete,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.ActivityLogService.create_log",
        fake_log,
    )

    with pytest.raises(HTTPException) as exc:
        await EmployerService.delete_employer(
            session=FakeSession(),
            user_id=uuid4(),
            actor={"user_id": str(uuid4())},
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Employer not found."
    assert captured["logged"] is False


@pytest.mark.asyncio
async def test_delete_employer_repository_failure_does_not_create_success_log(monkeypatch):
    captured = {"logged": False}

    async def fake_soft_delete(session, user_id):
        raise RuntimeError("database commit failed")

    async def fake_log(**kwargs):
        captured["logged"] = True

    monkeypatch.setattr(
        "app.service.super_admin.employer_service."
        "EmployerRepository.soft_delete_employer_by_user_id",
        fake_soft_delete,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.ActivityLogService.create_log",
        fake_log,
    )

    with pytest.raises(RuntimeError, match="database commit failed"):
        await EmployerService.delete_employer(
            session=FakeSession(),
            user_id=uuid4(),
            actor={"user_id": str(uuid4())},
        )

    assert captured["logged"] is False


@pytest.mark.asyncio
async def test_soft_deleted_employer_login_is_blocked(monkeypatch):
    async def fake_find_by_email(session, email):
        return SimpleNamespace(deleted_flag=True, password_hash="unused")

    monkeypatch.setattr(
        "app.service.authentication.auth_service.UsersRepository.find_by_email",
        fake_find_by_email,
    )

    with pytest.raises(HTTPException) as exc:
        await AuthService.login_service(
            session=FakeSession(),
            login=SimpleNamespace(email="ravi@example.com", password="Password1!"),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found!"
