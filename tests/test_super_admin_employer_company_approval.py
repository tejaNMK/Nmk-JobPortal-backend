from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import super_admin_only
from app.main import init_app
from app.service.super_admin.employer_service import EmployerService


class FakeSession:
    pass


async def fake_db():
    yield FakeSession()


def _employer(**overrides):
    data = {
        "id": "employer-1",
        "verification_status": "PENDING",
        "is_verified": 0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_approve_employer_company_success(monkeypatch):
    updated = SimpleNamespace(company_name="NMK Technologies")
    captured = {"approved": False, "logged": False}

    async def fake_get_employer(session, employer_id):
        return SimpleNamespace(user_id=uuid4()), _employer(id=employer_id)

    async def fake_approve(session, employer_id):
        captured["approved"] = True
        return SimpleNamespace(user_id=uuid4()), _employer(
            id=employer_id,
            verification_status="APPROVED",
            is_verified=1,
        )

    async def fake_log(**kwargs):
        captured["logged"] = True

    async def fake_details(session, employer_id):
        return updated

    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_employer",
        fake_get_employer,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.approve_employer_company",
        fake_approve,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.ActivityLogService.create_log",
        fake_log,
    )
    monkeypatch.setattr(EmployerService, "get_employer", fake_details)

    result = await EmployerService.approve_employer_company(
        session=FakeSession(),
        employer_id="employer-1",
        actor={"user_id": "admin-1"},
    )

    assert result is updated
    assert captured == {"approved": True, "logged": True}


@pytest.mark.asyncio
async def test_approve_employer_company_not_found(monkeypatch):
    async def fake_get_employer(session, employer_id):
        return None

    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_employer",
        fake_get_employer,
    )

    with pytest.raises(HTTPException) as exc:
        await EmployerService.approve_employer_company(
            session=FakeSession(),
            employer_id="missing-employer",
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Employer not found."


@pytest.mark.asyncio
async def test_approve_employer_company_rejects_already_approved(monkeypatch):
    async def fake_get_employer(session, employer_id):
        return SimpleNamespace(user_id=uuid4()), _employer(
            verification_status="APPROVED",
            is_verified=1,
        )

    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_employer",
        fake_get_employer,
    )

    with pytest.raises(HTTPException) as exc:
        await EmployerService.approve_employer_company(
            session=FakeSession(),
            employer_id="employer-1",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Company is already approved."


def test_approve_employer_company_endpoint_success(monkeypatch):
    app = init_app()
    response_data = {
        "employer_id": "employer-1",
        "company_name": "NMK Technologies",
        "verification_status": "APPROVED",
    }

    async def fake_super_admin():
        return {"user_id": "admin-1"}

    async def fake_approve(session, employer_id, actor):
        return SimpleNamespace(model_dump=lambda: response_data)

    from app.dependencies.role_dependencies import super_admin_only

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[super_admin_only] = fake_super_admin

    monkeypatch.setattr(EmployerService, "approve_employer_company", fake_approve)
    response = TestClient(app).patch("/super-admin/employers/employer-1/approve")

    assert response.status_code == 200
    assert response.json()["message"] == "Company approved successfully."
    assert response.json()["data"] == response_data


def test_approve_employer_company_endpoint_requires_auth():
    app = init_app()
    app.dependency_overrides[get_db] = fake_db

    response = TestClient(app).patch("/super-admin/employers/employer-1/approve")

    assert response.status_code == 401
    assert response.json()["message"] == "Missing or invalid authorization token"


def test_approve_employer_company_endpoint_rejects_non_super_admin(monkeypatch):
    app = init_app()

    async def fake_payload():
        return {"user_id": "candidate-1"}

    async def fake_find_user(session, user_id):
        return SimpleNamespace(
            roles=[SimpleNamespace(role_code="ROLE_CANDIDATE")]
        )

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    monkeypatch.setattr(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        fake_find_user,
    )

    response = TestClient(app).patch(
        "/super-admin/employers/employer-1/approve",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "Only Super Admin can access this resource"


@pytest.mark.asyncio
async def test_super_admin_guard_accepts_legacy_super_admin_role_code(monkeypatch):
    async def fake_find_user(session, user_id):
        return SimpleNamespace(
            roles=[SimpleNamespace(role_code="SUPER_ADMIN")]
        )

    monkeypatch.setattr(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        fake_find_user,
    )

    payload = {"user_id": "admin-1"}

    assert await super_admin_only(payload=payload, session=FakeSession()) is payload


@pytest.mark.asyncio
async def test_super_admin_guard_accepts_super_admin_role_name(monkeypatch):
    async def fake_find_user(session, user_id):
        return SimpleNamespace(
            roles=[SimpleNamespace(role_code=None, role_name="Super Admin")]
        )

    monkeypatch.setattr(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        fake_find_user,
    )

    payload = {"user_id": "admin-1"}

    assert await super_admin_only(payload=payload, session=FakeSession()) is payload
