from datetime import datetime, timezone
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.repository.employer_repository.job_repo import (
    DUPLICATE_JOB_MESSAGE,
    normalize_job_duplicate_text,
)
from app.schema.job import PostJobRequestSchema
from app.service.employer_service.job_idempotency_errors import DuplicateJobPostingError
from app.service.employer_service.job_service import JobService


class FakeSession:
    pass


VALID_JOB_BODY = {
    "job_title": "Python Backend Developer",
    "job_description": "Build APIs",
    "employment_type": "Full Time",
    "experience_required": "2-5",
    "location": "Hyderabad",
    "work_mode": "remote",
    "skills": ["Python", "FastAPI"],
    "salary_range": "800000-1200000",
    "number_of_openings": 2,
    "application_deadline": "2099-12-31T23:59:59+00:00",
    "company_name": "NMK Technologies",
    "contact_email": "hr@nmktechnologies.com",
    "status": "published",
}


def _request(**overrides) -> PostJobRequestSchema:
    payload = {**VALID_JOB_BODY, **overrides}
    return PostJobRequestSchema(**payload)


def _job(**overrides):
    data = {
        "job_id": "job-1",
        "employer_id": "employer-1",
        "title": "Python Backend Developer",
        "description": "Build APIs",
        "employment_type": "FULL_TIME",
        "experience_min": 2,
        "experience_max": 5,
        "location": "Hyderabad",
        "work_mode": "REMOTE",
        "skills": [],
        "salary_min": 800000.0,
        "salary_max": 1200000.0,
        "no_of_openings": 2,
        "application_deadline": None,
        "company_name": "NMK Technologies",
        "contact_email": "hr@nmktechnologies.com",
        "status": "PUBLISHED",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Python Developer", "python developer"),
        (" python developer ", "python developer"),
        ("PYTHON   DEVELOPER", "python developer"),
    ],
)
def test_duplicate_text_normalization(raw, expected):
    assert normalize_job_duplicate_text(raw) == expected


@pytest.mark.asyncio
async def test_unique_job_is_created():
    created = _job()
    with patch.object(JobService, "_require_employer", new_callable=AsyncMock), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_idempotency_key",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.find_duplicate_active_job",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.create_job",
        new_callable=AsyncMock,
        return_value=created,
    ) as create_job:
        result = await JobService.create_post_job(
            session=FakeSession(),
            payload={"user_id": "11111111-1111-1111-1111-111111111111", "email": "hr@example.com"},
            employer_id="employer-1",
            request=_request(),
            idempotency_key=None,
        )

    assert result == created
    create_job.assert_awaited_once()


@pytest.mark.parametrize(
    "overrides",
    [
        {"company_name": "Different Company"},
        {"location": "Bengaluru"},
        {"employment_type": "Contract"},
    ],
)
@pytest.mark.asyncio
async def test_different_duplicate_fields_allow_creation(overrides):
    created = _job(**overrides)
    with patch.object(JobService, "_require_employer", new_callable=AsyncMock), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_idempotency_key",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.find_duplicate_active_job",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.create_job",
        new_callable=AsyncMock,
        return_value=created,
    ) as create_job:
        result = await JobService.create_post_job(
            session=FakeSession(),
            payload={"user_id": "11111111-1111-1111-1111-111111111111"},
            employer_id="employer-1",
            request=_request(**overrides),
            idempotency_key=None,
        )

    assert result == created
    create_job.assert_awaited_once()


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {
            "job_title": "PYTHON   BACKEND DEVELOPER",
            "company_name": "nmk technologies",
            "location": "hyderabad",
        },
        {
            "job_title": " python backend developer ",
            "company_name": " NMK   Technologies ",
            "location": " Hyderabad ",
        },
    ],
)
@pytest.mark.asyncio
async def test_duplicate_job_rejected_and_audited(overrides):
    duplicate = _job()
    with patch.object(JobService, "_require_employer", new_callable=AsyncMock), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_idempotency_key",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.find_duplicate_active_job",
        new_callable=AsyncMock,
        return_value=duplicate,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.log_duplicate_job_attempt",
        new_callable=AsyncMock,
    ) as audit_log, patch(
        "app.service.employer_service.job_service.JobRepository.create_job",
        new_callable=AsyncMock,
    ) as create_job:
        with pytest.raises(HTTPException) as exc_info:
            await JobService.create_post_job(
                session=FakeSession(),
                payload={"user_id": "11111111-1111-1111-1111-111111111111", "email": "hr@example.com"},
                employer_id="employer-1",
                request=_request(**overrides),
                idempotency_key=None,
                request_id="req-123",
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == DUPLICATE_JOB_MESSAGE
    audit_log.assert_awaited_once()
    create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_duplicate_integrity_error_returns_conflict_and_audits():
    with patch.object(JobService, "_require_employer", new_callable=AsyncMock), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_idempotency_key",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.find_duplicate_active_job",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.create_job",
        new_callable=AsyncMock,
        side_effect=DuplicateJobPostingError(employer_id="employer-1"),
    ), patch(
        "app.service.employer_service.job_service.JobRepository.log_duplicate_job_attempt",
        new_callable=AsyncMock,
    ) as audit_log:
        with pytest.raises(HTTPException) as exc_info:
            await JobService.create_post_job(
                session=FakeSession(),
                payload={"user_id": "11111111-1111-1111-1111-111111111111"},
                employer_id="employer-1",
                request=_request(),
                idempotency_key=None,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == DUPLICATE_JOB_MESSAGE
    audit_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_idempotency_key_returns_existing_job_without_duplicate_conflict():
    existing = _job(job_id="job-existing")
    with patch.object(JobService, "_require_employer", new_callable=AsyncMock), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_idempotency_key",
        new_callable=AsyncMock,
        return_value=existing,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.find_duplicate_active_job",
        new_callable=AsyncMock,
    ) as duplicate_lookup, patch(
        "app.service.employer_service.job_service.JobRepository.create_job",
        new_callable=AsyncMock,
    ) as create_job:
        result = await JobService.create_post_job(
            session=FakeSession(),
            payload={"user_id": "11111111-1111-1111-1111-111111111111"},
            employer_id="employer-1",
            request=_request(),
            idempotency_key="idem-1",
        )

    assert result == existing
    duplicate_lookup.assert_not_awaited()
    create_job.assert_not_awaited()


def test_duplicate_through_api_returns_existing_error_envelope():
    botocore_module = types.ModuleType("botocore")
    botocore_exceptions_module = types.ModuleType("botocore.exceptions")
    botocore_exceptions_module.ClientError = Exception
    sys.modules.setdefault("botocore", botocore_module)
    sys.modules.setdefault("botocore.exceptions", botocore_exceptions_module)

    from app.main import init_app

    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "email": "hr@example.com",
        }

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    client = TestClient(app)

    with patch(
        "app.controller.employer_controller.job._get_or_create_employer_profile",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(id="employer-1"),
    ), patch(
        "app.controller.employer_controller.job.JobService.create_post_job",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=409, detail=DUPLICATE_JOB_MESSAGE),
    ):
        response = client.post("/jobs/", json=VALID_JOB_BODY)

    body = response.json()
    assert response.status_code == 409
    assert body["success"] is False
    assert body["status"] == 409
    assert body["message"] == DUPLICATE_JOB_MESSAGE
    assert body["error"]["code"] == "CONFLICT"
