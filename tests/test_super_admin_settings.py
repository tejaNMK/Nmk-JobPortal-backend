from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.utils.utc import utc_now_naive
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.middleware.maintenance_mode import (
    MAINTENANCE_MESSAGE,
    MaintenanceModeMiddleware,
    REGISTRATION_DISABLED_MESSAGE,
)
from app.schema.super_admin.settings import SystemSettingsUpdateRequest
from app.service.super_admin.settings_service import SystemSettingsService


class FakeSession:
    def add(self, obj):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSessionFactory:
    def __call__(self):
        return FakeSession()


def _settings(**overrides):
    data = {
        "id": uuid4(),
        "maintenance_mode": False,
        "registration_enabled": True,
        "candidate_default_subscription_plan": "candidate-free",
        "employer_default_subscription_plan": "employer-free",
        "password_policy": {
            "min_length": 8,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_number": True,
            "require_special_character": False,
        },
        "email_notifications": {
            "enabled": True,
            "company_approval_updates": True,
            "subscription_updates": True,
            "system_alerts": True,
        },
        "platform_config": {
            "platform_name": "Old Portal",
            "support_email": "old@example.com",
            "timezone": "Asia/Kolkata",
        },
        "updated_at": utc_now_naive(),
        "updated_by": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_settings_patch_merges_only_supplied_fields(monkeypatch):
    existing = _settings()
    captured_updates = {}

    async def fake_get_active(session):
        return existing

    async def fake_update(session, settings, updates, updated_by):
        captured_updates.update(updates)
        for key, value in updates.items():
            if key in {"password_policy", "email_notifications", "platform_config"}:
                setattr(settings, key, {**getattr(settings, key), **value})
            else:
                setattr(settings, key, value)
        settings.updated_by = updated_by
        return settings

    async def fake_log(**kwargs):
        return None

    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.update",
        fake_update,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.ActivityLogService.create_log",
        fake_log,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SubscriptionBootstrapService.bootstrap_defaults_and_assignments",
        lambda **kwargs: None,
    )

    response = await SystemSettingsService.update_settings(
        session=FakeSession(),
        request=SystemSettingsUpdateRequest(
            maintenance_mode=True,
            minimum_password_length=10,
            require_special_character=True,
            platform_name="NMK Job Portal",
        ),
        actor={"user_id": "admin-1"},
    )

    assert captured_updates == {
        "maintenance_mode": True,
        "password_policy": {
            "min_length": 10,
            "require_special_character": True,
        },
        "platform_config": {
            "platform_name": "NMK Job Portal",
        },
    }
    assert response.maintenance_mode is True
    assert response.password_policy["require_uppercase"] is True
    assert response.password_policy["min_length"] == 10
    assert response.platform_config["support_email"] == "old@example.com"
    assert not hasattr(response, "extra_config")


@pytest.mark.asyncio
async def test_settings_get_returns_updated_by_display_details(monkeypatch):
    updater_id = str(uuid4())
    existing = _settings(updated_by=updater_id)

    async def fake_get_active(session):
        return existing

    async def fake_find_by_user_id(session, user_id):
        assert user_id == updater_id
        return SimpleNamespace(
            first_name="Super",
            last_name="Admin",
            email="superadmin@nmk.com",
            password_hash="secret",
            roles=[SimpleNamespace(role_code="ROLE_SUPER_ADMIN")],
        )

    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.UsersRepository.find_by_user_id",
        fake_find_by_user_id,
    )

    response = await SystemSettingsService.get_settings(session=FakeSession())
    payload = response.model_dump()

    assert response.updated_by == updater_id
    assert response.updated_by_email == "superadmin@nmk.com"
    assert response.updated_by_name == "Super Admin"
    assert response.updated_by_role == "ROLE_SUPER_ADMIN"
    assert "password_hash" not in payload


@pytest.mark.asyncio
async def test_settings_get_missing_updater_returns_safe_fallback(monkeypatch):
    updater_id = str(uuid4())
    existing = _settings(updated_by=updater_id)

    async def fake_get_active(session):
        return existing

    async def fake_find_by_user_id(session, user_id):
        return None

    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.UsersRepository.find_by_user_id",
        fake_find_by_user_id,
    )

    response = await SystemSettingsService.get_settings(session=FakeSession())

    assert response.updated_by == updater_id
    assert response.updated_by_email is None
    assert response.updated_by_name == "Unknown User"
    assert response.updated_by_role is None


@pytest.mark.asyncio
async def test_settings_get_null_updated_by_returns_null_identity(monkeypatch):
    existing = _settings(updated_by=None)

    async def fake_get_active(session):
        return existing

    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.get_active",
        fake_get_active,
    )

    response = await SystemSettingsService.get_settings(session=FakeSession())

    assert response.updated_by is None
    assert response.updated_by_email is None
    assert response.updated_by_name is None
    assert response.updated_by_role is None


@pytest.mark.asyncio
async def test_settings_patch_accepts_valid_timezone(monkeypatch):
    existing = _settings()
    captured_updates = {}

    async def fake_get_active(session):
        return existing

    async def fake_update(session, settings, updates, updated_by):
        captured_updates.update(updates)
        for key, value in updates.items():
            if key in {"password_policy", "email_notifications", "platform_config"}:
                setattr(settings, key, {**getattr(settings, key), **value})
            else:
                setattr(settings, key, value)
        return settings

    async def fake_log(**kwargs):
        return None

    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.update",
        fake_update,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.ActivityLogService.create_log",
        fake_log,
    )

    response = await SystemSettingsService.update_settings(
        session=FakeSession(),
        request=SystemSettingsUpdateRequest(timezone="Asia/Kolkata"),
        actor={"user_id": "admin-1"},
    )

    assert captured_updates["platform_config"] == {"timezone": "Asia/Kolkata"}
    assert response.platform_config["timezone"] == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_settings_patch_sets_audit_from_authenticated_actor(monkeypatch):
    existing = _settings()
    actor_id = str(uuid4())
    updated_at = datetime(2026, 8, 3, 10, 38, 0)
    captured_updated_by = None

    async def fake_get_active(session):
        return existing

    async def fake_update(session, settings, updates, updated_by):
        nonlocal captured_updated_by
        captured_updated_by = updated_by
        for key, value in updates.items():
            setattr(settings, key, value)
        settings.updated_by = updated_by
        settings.updated_at = updated_at
        return settings

    async def fake_find_by_user_id(session, user_id):
        return SimpleNamespace(
            first_name="Super",
            last_name="Admin",
            email="superadmin@nmk.com",
            roles=[SimpleNamespace(role_code="ROLE_SUPER_ADMIN")],
        )

    async def fake_log(**kwargs):
        return None

    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.update",
        fake_update,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.UsersRepository.find_by_user_id",
        fake_find_by_user_id,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.ActivityLogService.create_log",
        fake_log,
    )

    response = await SystemSettingsService.update_settings(
        session=FakeSession(),
        request=SystemSettingsUpdateRequest(platform_name="NMK Job Portal"),
        actor={"user_id": actor_id},
    )

    assert captured_updated_by == actor_id
    assert response.updated_by == actor_id
    assert response.updated_at == updated_at
    assert response.updated_by_email == "superadmin@nmk.com"
    assert response.updated_by_name == "Super Admin"


def test_settings_patch_rejects_invalid_timezone():
    with pytest.raises(ValueError) as exc:
        SystemSettingsUpdateRequest(timezone="Mars/Olympus")

    assert "Timezone must be a valid IANA timezone name" in str(exc.value)


@pytest.mark.asyncio
async def test_settings_patch_rejects_inactive_default_subscription(monkeypatch):
    existing = _settings(candidate_default_subscription_plan=None)
    subscription_id = uuid4()

    async def fake_get_active(session):
        return existing

    async def fake_get_by_id(session, subscription_id):
        return SimpleNamespace(
            subscription_id=subscription_id,
            subscription_type="CANDIDATE",
            is_active=False,
        )

    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SubscriptionRepository.get_by_id",
        fake_get_by_id,
    )

    with pytest.raises(HTTPException) as exc:
        await SystemSettingsService.update_settings(
            session=FakeSession(),
            request=SystemSettingsUpdateRequest(
                candidate_default_subscription_plan=str(subscription_id),
            ),
            actor={"user_id": "admin-1"},
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_settings_patch_backfills_when_default_subscription_changes(monkeypatch):
    existing = _settings(candidate_default_subscription_plan=None)
    subscription_id = uuid4()
    backfill_called = False

    async def fake_get_active(session):
        return existing

    async def fake_get_by_id(session, subscription_id):
        return SimpleNamespace(
            subscription_id=subscription_id,
            subscription_type="CANDIDATE",
            is_active=True,
        )

    async def fake_clear_default_for_type(**kwargs):
        return None

    async def fake_update(session, settings, updates, updated_by):
        for key, value in updates.items():
            setattr(settings, key, value)
        return settings

    async def fake_backfill(**kwargs):
        nonlocal backfill_called
        backfill_called = True
        return {"subscriptions_assigned": 1}

    async def fake_log(**kwargs):
        return None

    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SubscriptionRepository.get_by_id",
        fake_get_by_id,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SubscriptionRepository.clear_default_for_type",
        fake_clear_default_for_type,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SystemSettingsRepository.update",
        fake_update,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.SubscriptionBootstrapService.backfill_missing_user_subscriptions",
        fake_backfill,
    )
    monkeypatch.setattr(
        "app.service.super_admin.settings_service.ActivityLogService.create_log",
        fake_log,
    )

    response = await SystemSettingsService.update_settings(
        session=FakeSession(),
        request=SystemSettingsUpdateRequest(
            candidate_default_subscription_plan=str(subscription_id),
        ),
        actor={"user_id": "admin-1"},
    )

    assert response.candidate_default_subscription_plan == str(subscription_id)
    assert backfill_called is True


def _middleware_client(monkeypatch, settings, is_super_admin=False):
    app = FastAPI()
    app.add_middleware(MaintenanceModeMiddleware)

    @app.get("/public")
    async def public():
        return {"ok": True}

    @app.post("/auth/candidate/register")
    async def register():
        return {"ok": True}

    @app.get("/candidate/profile")
    async def candidate_profile():
        return {"ok": True}

    @app.get("/super-admin/dashboard")
    async def super_admin_dashboard():
        return {"ok": True}

    async def fake_get_active(session):
        return settings

    async def fake_find_user(session, user_id):
        role = SimpleNamespace(
            role_code="ROLE_SUPER_ADMIN" if is_super_admin else "ROLE_CANDIDATE"
        )
        return SimpleNamespace(roles=[role])

    monkeypatch.setattr(
        "app.middleware.maintenance_mode.AsyncSessionLocal",
        FakeSessionFactory(),
    )
    monkeypatch.setattr(
        "app.middleware.maintenance_mode.SystemSettingsRepository.get_active",
        fake_get_active,
    )
    monkeypatch.setattr(
        "app.middleware.maintenance_mode.JWTRepo.extract_token",
        lambda token: {"user_id": "user-1"},
    )
    monkeypatch.setattr(
        "app.middleware.maintenance_mode.UsersRepository.find_by_user_id",
        fake_find_user,
    )
    return TestClient(app)


def test_maintenance_mode_blocks_public_and_candidate_requests(monkeypatch):
    client = _middleware_client(
        monkeypatch,
        _settings(maintenance_mode=True),
    )

    response = client.get("/public")
    assert response.status_code == 503
    assert response.json() == {"message": MAINTENANCE_MESSAGE}

    response = client.get(
        "/candidate/profile",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 503
    assert response.json() == {"message": MAINTENANCE_MESSAGE}


def test_settings_patch_rejects_unknown_nested_fields():
    with pytest.raises(ValueError):
        SystemSettingsUpdateRequest(password_policy={"unused": True})

    with pytest.raises(ValueError):
        SystemSettingsUpdateRequest(email_notifications={"unused": True})

    with pytest.raises(ValueError):
        SystemSettingsUpdateRequest(platform_config={"unused": True})


def test_settings_patch_rejects_audit_fields():
    for field in (
        "updated_by",
        "updated_by_email",
        "updated_by_name",
        "updated_by_role",
        "updated_at",
    ):
        with pytest.raises(ValueError):
            SystemSettingsUpdateRequest(**{field: "malicious"})


def test_maintenance_mode_allows_super_admin_operations(monkeypatch):
    super_admin_path_client = _middleware_client(
        monkeypatch,
        _settings(maintenance_mode=True),
    )
    response = super_admin_path_client.get("/super-admin/dashboard")
    assert response.status_code == 200

    super_admin_token_client = _middleware_client(
        monkeypatch,
        _settings(maintenance_mode=True),
        is_super_admin=True,
    )
    response = super_admin_token_client.get(
        "/candidate/profile",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200


def test_registration_disabled_blocks_only_registration(monkeypatch):
    client = _middleware_client(
        monkeypatch,
        _settings(registration_enabled=False),
    )

    response = client.post("/auth/candidate/register")
    assert response.status_code == 403
    assert response.json() == {"message": REGISTRATION_DISABLED_MESSAGE}

    response = client.get("/public")
    assert response.status_code == 200
