from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schema.employer import EmployerRegisterSchema
from app.service.authentication.auth_service import AuthService
from app.service.super_admin.employer_service import EmployerService


class FakeSession:
    async def rollback(self):
        pass


def _user(*, email_verified=False, mobile_verified=False):
    return SimpleNamespace(
        user_id=uuid4(),
        first_name="Ravi",
        last_name="Kumar",
        email="ravi@example.com",
        mobile_number="+919876543210",
        email_verified=email_verified,
        mobile_verified=mobile_verified,
        created_at=datetime(2026, 8, 5, 9, 12, 3, 221000),
        last_login_at=None,
        roles=[],
    )


def _employer(**overrides):
    data = {
        "id": "employer-1",
        "company_name": "NMK Technologies",
        "company_logo_url": None,
        "company_description": None,
        "industry": "IT",
        "website_url": None,
        "company_website": None,
        "verification_status": "APPROVED",
        "rejection_reason": None,
        "status": "ACTIVE",
        "suspension_reason": None,
        "created_at": "2026-08-02T00:00:00",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _register_payload():
    return EmployerRegisterSchema(
        company_name="NMK Technologies",
        first_name="Ravi",
        middle_name="K",
        last_name="Kumar",
        website="https://example.com",
        work_email="ravi@example.com",
        country_code="+91",
        phone_number="98765 43210",
        password="StrongPass1!",
        confirm_password="StrongPass1!",
        team_size="11-50",
        agree_to_terms=True,
    )


@pytest.mark.parametrize(
    ("email_verified", "mobile_verified", "expected"),
    [
        (True, True, "VERIFIED"),
        (True, False, "PARTIALLY_VERIFIED"),
        (False, True, "PARTIALLY_VERIFIED"),
        (False, False, "NOT_VERIFIED"),
    ],
)
def test_contact_verification_status_values(
    email_verified,
    mobile_verified,
    expected,
):
    assert (
        EmployerService._verification_status(
            email_verified=email_verified,
            mobile_verified=mobile_verified,
        )
        == expected
    )


@pytest.mark.asyncio
async def test_employer_list_returns_user_contact_verification(monkeypatch):
    users_and_employers = [
        (_user(email_verified=True, mobile_verified=True), _employer(id="full"), "Premium"),
        (_user(email_verified=True, mobile_verified=False), _employer(id="partial"), None),
        (_user(email_verified=False, mobile_verified=False), _employer(id="none"), None),
    ]

    async def fake_list_employers(session, page, page_size, search, sort_by, sort_order):
        assert sort_by == "created_at"
        assert sort_order == "desc"
        return users_and_employers, len(users_and_employers)

    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.list_employers",
        fake_list_employers,
    )

    response = await EmployerService.list_employers(
        session=FakeSession(),
        page=1,
        page_size=10,
        search=None,
    )

    assert response.total == 3
    assert [item.verification_status for item in response.items] == [
        "VERIFIED",
        "PARTIALLY_VERIFIED",
        "NOT_VERIFIED",
    ]
    assert response.items[0].email_verified is True
    assert response.items[0].mobile_verified is True
    assert response.items[0].company_verification_status == "APPROVED"
    assert response.items[0].created_at == datetime(2026, 8, 5, 9, 12, 3, 221000)


@pytest.mark.asyncio
async def test_employer_detail_returns_same_contact_verification(monkeypatch):
    async def fake_get_employer(session, employer_id):
        return _user(email_verified=True, mobile_verified=True), _employer(id=employer_id)

    async def fake_job_counts(session, employer_id):
        return {"total_jobs": 2, "active_jobs": 1, "closed_jobs": 1}

    async def fake_subscription(session, user_id):
        return None

    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_employer",
        fake_get_employer,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_job_counts",
        fake_job_counts,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_active_subscription",
        fake_subscription,
    )

    response = await EmployerService.get_employer(
        session=FakeSession(),
        employer_id="employer-1",
    )

    assert response.email_verified is True
    assert response.mobile_verified is True
    assert response.verification_status == "VERIFIED"
    assert response.company_verification_status == "APPROVED"


@pytest.mark.asyncio
async def test_legacy_backfilled_employer_displays_verified(monkeypatch):
    async def fake_get_employer(session, employer_id):
        legacy_user = _user(email_verified=True, mobile_verified=True)
        legacy_employer = _employer(id=employer_id, verification_status="APPROVED")
        return legacy_user, legacy_employer

    async def fake_job_counts(session, employer_id):
        return {"total_jobs": 0, "active_jobs": 0, "closed_jobs": 0}

    async def fake_subscription(session, user_id):
        return None

    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_employer",
        fake_get_employer,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_job_counts",
        fake_job_counts,
    )
    monkeypatch.setattr(
        "app.service.super_admin.employer_service.EmployerRepository.get_active_subscription",
        fake_subscription,
    )

    response = await EmployerService.get_employer(
        session=FakeSession(),
        employer_id="legacy-employer",
    )

    assert response.verification_status == "VERIFIED"
    assert response.email_verified is True
    assert response.mobile_verified is True


@pytest.mark.asyncio
async def test_employer_registration_requires_email_verification(monkeypatch):
    async def fake_validate_unique_contact(session, email, mobile_number):
        return None

    async def fake_verified_email(session, email):
        return None

    monkeypatch.setattr(AuthService, "_validate_unique_contact", fake_validate_unique_contact)
    monkeypatch.setattr(
        "app.service.authentication.auth_service.EmailVerificationTokenRepository.find_recently_verified_token",
        fake_verified_email,
    )

    with pytest.raises(HTTPException) as exc:
        await AuthService.employer_register_service(FakeSession(), _register_payload())

    assert exc.value.status_code == 400
    assert exc.value.detail == "Please verify your email before registration."


@pytest.mark.asyncio
async def test_employer_registration_requires_mobile_verification(monkeypatch):
    async def fake_validate_unique_contact(session, email, mobile_number):
        return None

    async def fake_verified_email(session, email):
        return SimpleNamespace()

    async def fake_verified_mobile(session, country_code, mobile_number):
        return None

    monkeypatch.setattr(AuthService, "_validate_unique_contact", fake_validate_unique_contact)
    monkeypatch.setattr(
        "app.service.authentication.auth_service.EmailVerificationTokenRepository.find_recently_verified_token",
        fake_verified_email,
    )
    monkeypatch.setattr(
        "app.service.authentication.auth_service.MobileVerificationRepository.get_verified_mobile",
        fake_verified_mobile,
    )

    with pytest.raises(HTTPException) as exc:
        await AuthService.employer_register_service(FakeSession(), _register_payload())

    assert exc.value.status_code == 400
    assert exc.value.detail == "Please verify your mobile number before registration."
