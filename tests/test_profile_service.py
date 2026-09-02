from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.utils.utc import utc_now_naive

from app.schema.profile import EmployerProfileUpdate
from app.service.profile_service import (
    CompanyProfileService,
    EmployerProfileService,
    _serialize_company,
)


class FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class FakeUpload:
    filename = "logo.png"
    content_type = "image/png"

    async def read(self):
        return b"image-bytes"


def _employer(**overrides):
    data = {
        "id": "emp-1",
        "user_id": uuid4(),
        "job_title": "Recruiter",
        "department": None,
        "bio": None,
        "location": None,
        "timezone": None,
        "experience_years": None,
        "candidate_response_time": None,
        "interview_mode": None,
        "availability": None,
        "languages": None,
        "linkedin_url": None,
        "website_url": None,
        "profile_photo": None,
        "visibility": "PRIVATE",
        "specialization_1": None,
        "specialization_2": None,
        "specialization_3": None,
        "specialization_4": None,
        "created_at": utc_now_naive().isoformat(),
        "updated_at": utc_now_naive().isoformat(),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _company(**overrides):
    data = {
        "id": uuid4(),
        "company_id": "company-1",
        "company_name": "NMK Global",
        "website": None,
        "industry": None,
        "company_size": None,
        "size": None,
        "founded_year": None,
        "description": None,
        "headquarters_country": None,
        "headquarters_state": None,
        "headquarters_city": None,
        "logo_url": None,
        "logo_path": None,
        "contact_email": None,
        "contact_phone": None,
        "verification_status": "PENDING",
        "verified_at": None,
        "is_public": False,
        "created_at": utc_now_naive(),
        "updated_at": utc_now_naive(),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_employer_profile_partial_update_only_supplied_fields():
    user_id = uuid4()
    profile = _employer(user_id=user_id, bio="Old bio", department="People")
    request = EmployerProfileUpdate(bio="Senior Technical Recruiter")
    session = FakeSession()

    with patch(
        "app.service.profile_service.EmployerProfileRepository.get_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.service.profile_service.EmployerProfileRepository.save",
        new_callable=AsyncMock,
        side_effect=lambda session, profile: profile,
    ) as save:
        result = await EmployerProfileService.update(
            session=session,
            payload={"user_id": str(user_id)},
            request=request,
        )

    assert profile.bio == "Senior Technical Recruiter"
    assert profile.department == "People"
    assert profile.updated_by == str(user_id)
    assert session.committed is True
    assert result.bio == "Senior Technical Recruiter"
    save.assert_awaited_once()


def test_profile_completion_lists_missing_fields():
    profile = _employer(
        profile_photo="/uploads/me.png",
        bio="Hiring engineers",
        job_title="Lead Recruiter",
        department="Engineering",
        experience_years=8,
        languages=["English"],
        linkedin_url="https://linkedin.com/in/example",
        location="Hyderabad",
    )

    completion = EmployerProfileService.calculate_profile_completion(profile)

    assert completion.completion_percentage == 80
    assert completion.missing_fields == ["website_url", "specializations"]


def test_serialize_company_accepts_offset_without_colon():
    profile = _company(
        created_at="2026-07-10 19:37:21.444349+00",
        updated_at="2026-07-10 19:37:21.444349+00",
    )

    response = _serialize_company(profile)

    assert isinstance(response.created_at, datetime)
    assert isinstance(response.updated_at, datetime)
    assert response.created_at.year == 2026
    assert response.updated_at.year == 2026


@pytest.mark.asyncio
async def test_employer_dashboard_computes_dynamic_summary():
    user_id = uuid4()
    profile = _employer(
        user_id=user_id,
        profile_photo="/uploads/me.png",
        bio="Hiring engineers",
        job_title="Lead Recruiter",
        department="Engineering",
        experience_years=8,
        languages=["English"],
        linkedin_url="https://linkedin.com/in/example",
        website_url="https://example.com",
        specialization_1="Backend",
        location="Hyderabad",
    )
    job = SimpleNamespace(
        job_id="job-1",
        title="Python Developer",
        status="PUBLISHED",
        location="Remote",
    )
    activity = SimpleNamespace(
        audit_id=1,
        event_type="JOB_CREATED",
        message="Job created",
        created_at=utc_now_naive(),
        job_id="job-1",
    )

    with patch.multiple(
        "app.service.profile_service.EmployerProfileRepository",
        get_by_user_id=AsyncMock(return_value=profile),
        count_responded_applications=AsyncMock(return_value=(9, 10)),
        fetch_active_jobs=AsyncMock(return_value=[job]),
        fetch_recent_activity=AsyncMock(return_value=[(activity, job)]),
        count_candidates_contacted=AsyncMock(return_value=342),
        count_interviews_scheduled=AsyncMock(return_value=58),
        average_candidate_rating=AsyncMock(return_value=4.8),
    ):
        summary = await EmployerProfileService.dashboard(
            session=FakeSession(),
            payload={"user_id": str(user_id)},
        )

    assert summary.profile_completion == 100
    assert summary.candidates_contacted == 342
    assert summary.response_rate == 90
    assert summary.interviews_scheduled == 58
    assert summary.candidate_rating == 4.8
    assert summary.active_jobs[0]["job_id"] == "job-1"
    assert summary.recent_activity[0]["activity_type"] == "JOB_CREATED"
    assert summary.recent_activity[0]["message"] == 'Created job "Python Developer"'
    assert summary.recent_activity[0]["description"] == 'Created job "Python Developer"'


@pytest.mark.asyncio
async def test_upload_employer_photo_uses_s3_and_returns_presigned_url():
    user_id = uuid4()
    profile = _employer(user_id=user_id, profile_photo=None)
    session = FakeSession()

    with patch(
        "app.service.profile_service.EmployerProfileRepository.get_by_user_id",
        new_callable=AsyncMock,
        return_value=profile,
    ), patch(
        "app.service.profile_service.EmployerProfileRepository.save",
        new_callable=AsyncMock,
        side_effect=lambda session, profile: profile,
    ), patch(
        "app.service.profile_service.s3_service.upload_employer_profile_photo",
        return_value="employer-profile-images/emp-1/profile.png",
    ) as upload, patch(
        "app.service.profile_service.s3_service.generate_presigned_url",
        return_value="https://signed.example/employer-profile-images/emp-1/profile.png",
    ):
        result = await EmployerProfileService.upload_photo(
            session=session,
            payload={"user_id": str(user_id)},
            upload=FakeUpload(),
        )

    upload.assert_called_once()
    assert profile.profile_photo == "employer-profile-images/emp-1/profile.png"
    assert result.profile_photo == "https://signed.example/employer-profile-images/emp-1/profile.png"


@pytest.mark.asyncio
async def test_upload_company_logo_uses_s3_and_returns_presigned_url():
    user_id = uuid4()
    employer = _employer(user_id=user_id)
    company = _company()
    session = FakeSession()

    with patch(
        "app.service.profile_service.EmployerProfileRepository.get_by_user_id",
        new_callable=AsyncMock,
        return_value=employer,
    ), patch(
        "app.service.profile_service.CompanyProfileRepository.get_by_employer_id",
        new_callable=AsyncMock,
        return_value=company,
    ), patch(
        "app.service.profile_service.CompanyProfileRepository.save",
        new_callable=AsyncMock,
        side_effect=lambda session, profile: profile,
    ), patch(
        "app.service.profile_service.s3_service.upload_company_logo",
        return_value="company-logos/company-1/logo.png",
    ) as upload, patch(
        "app.service.profile_service.s3_service.generate_presigned_url",
        return_value="https://signed.example/company-logos/company-1/logo.png",
    ):
        result = await CompanyProfileService.upload_logo(
            session=session,
            payload={"user_id": str(user_id)},
            upload=FakeUpload(),
        )

    upload.assert_called_once()
    assert company.logo_url == "company-logos/company-1/logo.png"
    assert company.logo_path == "company-logos/company-1/logo.png"
    assert result.logo_url == "https://signed.example/company-logos/company-1/logo.png"
