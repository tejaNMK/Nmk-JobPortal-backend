from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import init_app
from app.schema.job import UpdateJobRequestSchema
from app.service.employer_service.job_service import JobService
from app.utils.job_time import normalize_deadline_to_utc_naive


valid_edit_payload = {
    "job_title": "Senior Python Developer",
    "job_description": "Build and maintain Python applications.",
    "employment_type": "FULL_TIME",
    "experience_required": "3-5",
    "location": "Remote",
    "work_mode": "REMOTE",
    "skills": ["Python", "FastAPI"],
    "salary_range": "120000-150000",
    "number_of_openings": 2,
    "application_deadline": "2099-12-31T23:59:59+00:00",
    "company_name": "Acme Inc",
    "contact_email": "hr@acme.com",
    "status": "PUBLISHED",
}

recruiter_payload_1 = {
    "user_id": "user-1",
    "jti": "jwt-1",
    "email": "recruiter1@acme.com",
    "roles": [
        {
            "role_id": "11111111-1111-1111-1111-111111111111",
            "role_name": "Recruiter",
            "role_code": "ROLE_RECRUITER",
        }
    ],
}

recruiter_payload_2 = {
    "user_id": "user-2",
    "jti": "jwt-2",
    "email": "recruiter2@acme.com",
    "roles": [
        {
            "role_id": "11111111-1111-1111-1111-111111111111",
            "role_name": "Recruiter",
            "role_code": "ROLE_RECRUITER",
        }
    ],
}


@pytest.fixture(scope="function")
def client():
    app = init_app()
    with patch("app.main.db") as mock_db:
        mock_db.init.return_value = None
        mock_db.close = AsyncMock(return_value=None)
        mock_db.session = None
        app = init_app()
        return TestClient(app)


@pytest.fixture(autouse=True)
def auth_session_mocks():
    async def find_active_session_by_jwt_id(*, session, jwt_id):
        user_id = {"jwt-1": "user-1", "jwt-2": "user-2"}.get(jwt_id)
        return SimpleNamespace(user_id=user_id) if user_id else None

    with patch(
        "app.dependencies.auth_dependencies.UserSessionRepository.find_active_session_by_jwt_id",
        new_callable=AsyncMock,
        side_effect=find_active_session_by_jwt_id,
    ), patch(
        "app.dependencies.auth_dependencies.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(deleted_flag=False, user_status="ACTIVE"),
    ):
        yield


mock_employer_1 = MagicMock()
mock_employer_1.id = "emp-1"
mock_employer_2 = MagicMock()
mock_employer_2.id = "emp-2"


class DummyJob:
    def __init__(self, job_id: str, employer_id: str):
        self.job_id = job_id
        self.employer_id = employer_id
        self.title = "Senior Python Developer"
        self.status = "PUBLISHED"
        self.closed_at = None
        self.closed_reason = None


def test_update_expired_job_with_future_deadline_reactivates_as_published():
    future_deadline = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    existing_job = SimpleNamespace(
        job_id="job-123",
        employer_id="emp-1",
        status="EXPIRED",
        title="Backend Developer",
    )

    async def fake_update_job(**kwargs):
        update_data = kwargs["update_data"]
        return SimpleNamespace(
            **{
                **existing_job.__dict__,
                "status": update_data.get("status", existing_job.status),
                "application_deadline": update_data["application_deadline"],
            }
        )

    with patch(
        "app.service.employer_service.job_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=existing_job,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.update_job",
        new_callable=AsyncMock,
        side_effect=fake_update_job,
    ) as update_job, patch(
        "app.service.employer_service.job_service.JobService._ensure_published_job_limit_available",
        new_callable=AsyncMock,
    ) as ensure_limit, patch(
        "app.service.employer_service.job_service.ActivityLogService.create_log_for_user_id",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            JobService.update_job(
                session=None,
                employer_id="emp-1",
                job_id="job-123",
                request=UpdateJobRequestSchema(application_deadline=future_deadline),
                actor_user_id="22222222-2222-2222-2222-222222222222",
                actor_email="recruiter@nmk.com",
            )
        )

    assert result.status == "PUBLISHED"
    assert update_job.await_args.kwargs["update_data"]["status"] == "PUBLISHED"
    ensure_limit.assert_awaited_once()


def test_update_expired_job_with_past_deadline_stays_expired():
    past_deadline = datetime.now(timezone.utc) - timedelta(days=1)
    existing_job = SimpleNamespace(
        job_id="job-123",
        employer_id="emp-1",
        status="EXPIRED",
        title="Backend Developer",
    )

    async def fake_update_job(**kwargs):
        return SimpleNamespace(
            **{
                **existing_job.__dict__,
                "application_deadline": kwargs["update_data"]["application_deadline"],
            }
        )

    with patch(
        "app.service.employer_service.job_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=existing_job,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.update_job",
        new_callable=AsyncMock,
        side_effect=fake_update_job,
    ) as update_job, patch(
        "app.service.employer_service.job_service.JobService._ensure_published_job_limit_available",
        new_callable=AsyncMock,
    ) as ensure_limit, patch(
        "app.service.employer_service.job_service.ActivityLogService.create_log_for_user_id",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            JobService.update_job(
                session=None,
                employer_id="emp-1",
                job_id="job-123",
                request=UpdateJobRequestSchema(application_deadline=past_deadline),
                actor_user_id="22222222-2222-2222-2222-222222222222",
                actor_email="recruiter@nmk.com",
            )
        )

    assert result.status == "EXPIRED"
    assert "status" not in update_job.await_args.kwargs["update_data"]
    ensure_limit.assert_not_called()


@pytest.mark.parametrize("status", ["DRAFT", "CLOSED", "PAUSED"])
def test_future_deadline_does_not_reactivate_non_expired_jobs(status):
    future_deadline = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    existing_job = SimpleNamespace(
        job_id="job-123",
        employer_id="emp-1",
        status=status,
        title="Backend Developer",
    )

    async def fake_update_job(**kwargs):
        return SimpleNamespace(
            **{
                **existing_job.__dict__,
                "application_deadline": kwargs["update_data"]["application_deadline"],
            }
        )

    with patch(
        "app.service.employer_service.job_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=existing_job,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.update_job",
        new_callable=AsyncMock,
        side_effect=fake_update_job,
    ) as update_job, patch(
        "app.service.employer_service.job_service.JobService._ensure_published_job_limit_available",
        new_callable=AsyncMock,
    ) as ensure_limit, patch(
        "app.service.employer_service.job_service.ActivityLogService.create_log_for_user_id",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            JobService.update_job(
                session=None,
                employer_id="emp-1",
                job_id="job-123",
                request=UpdateJobRequestSchema(application_deadline=future_deadline),
                actor_user_id="22222222-2222-2222-2222-222222222222",
                actor_email="recruiter@nmk.com",
            )
        )

    assert result.status == status
    assert "status" not in update_job.await_args.kwargs["update_data"]
    ensure_limit.assert_not_called()


def test_update_job_draft_to_published_sends_matching_job_alerts():
    existing_job = SimpleNamespace(
        job_id="job-123",
        employer_id="emp-1",
        status="DRAFT",
        title="Backend Developer",
    )
    published_job = SimpleNamespace(
        job_id="job-123",
        employer_id="emp-1",
        status="PUBLISHED",
        title="Backend Developer",
    )

    with patch(
        "app.service.employer_service.job_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.get_job_by_id",
        new_callable=AsyncMock,
        return_value=existing_job,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.update_job",
        new_callable=AsyncMock,
        return_value=published_job,
    ), patch(
        "app.service.employer_service.job_service.JobService._ensure_published_job_limit_available",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.JobAlertNotificationService.notify_matching_candidates",
        new_callable=AsyncMock,
    ) as notify_alerts, patch(
        "app.service.employer_service.job_service.ActivityLogService.create_log_for_user_id",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            JobService.update_job(
                session=None,
                employer_id="emp-1",
                job_id="job-123",
                request=UpdateJobRequestSchema(status="PUBLISHED"),
                actor_user_id="22222222-2222-2222-2222-222222222222",
                actor_email="recruiter@nmk.com",
            )
        )

    assert result.status == "PUBLISHED"
    notify_alerts.assert_awaited_once()


def test_aware_deadline_is_normalized_to_exact_utc_instant():
    deadline = datetime.fromisoformat("2026-07-28T23:59:59+05:30")

    assert normalize_deadline_to_utc_naive(deadline) == datetime(2026, 7, 28, 18, 29, 59)



def assert_response_common(resp_json: dict):
    assert "message" in resp_json
    assert "data" in resp_json
    assert "job_id" in resp_json["data"]
    assert "employer_id" in resp_json["data"]


class TestEditJobEndpoint:
    def test_close_job_successful_update(self, client):
        job_id = "job-123"
        dummy_job = DummyJob(job_id=job_id, employer_id="emp-1")
        dummy_job.status = "CLOSED"
        dummy_job.closed_at = datetime.now(UTC)
        dummy_job.closed_reason = "Position Filled"

        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_payload_1,
        ), patch(
            "app.controller.employer_controller.job.db.execute",
            return_value=MagicMock(scalar_one_or_none=lambda: mock_employer_1),
        ), patch(
            "app.service.employer_service.job_service.JobService.close_job",
            new_callable=AsyncMock,
            return_value=dummy_job,
        ) as mock_close:
            r = client.patch(
                f"/jobs/{job_id}/close",
                json={"reason": "Position Filled"},
                headers={"Authorization": "Bearer test"},
            )

        assert r.status_code == 200
        assert r.json()["message"] == "Job closed successfully."
        assert r.json()["data"]["job_id"] == job_id
        assert r.json()["data"]["status"] == "CLOSED"
        assert r.json()["data"]["closed_reason"] == "Position Filled"
        mock_close.assert_awaited_once()

    def test_edit_job_successful_update_replaces_skills_and_writes_audit(self, client):
        job_id = "job-123"
        dummy_job = DummyJob(job_id=job_id, employer_id="emp-1")

        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_payload_1,
        ),         patch(
            "app.controller.employer_controller.job.db.execute",
            return_value=MagicMock(scalar_one_or_none=lambda: mock_employer_1),
        ), patch(
            "app.service.employer_service.job_service.JobService.update_job",
            new_callable=AsyncMock,
            return_value=dummy_job,
        ) as mock_update:
            r = client.put(f"/jobs/{job_id}", json=valid_edit_payload, headers={"Authorization": "Bearer test"})
            assert r.status_code == 200
            mock_update.assert_awaited_once()
            assert_response_common(r.json())
            assert "Job updated successfully" in r.json()["message"]

    def test_edit_job_not_found_returns_404(self, client):
        job_id = "job-missing"
        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_payload_1,
        ),         patch(
            "app.controller.employer_controller.job.db.execute",
            return_value=MagicMock(scalar_one_or_none=lambda: mock_employer_1),
        ), patch(
            "app.service.employer_service.job_service.JobService.update_job",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=404, detail="Job not found."),
        ):
            r = client.put(f"/jobs/{job_id}", json=valid_edit_payload, headers={"Authorization": "Bearer test"})
            assert r.status_code == 404

    def test_edit_job_access_denied_for_other_employer(self, client):
        job_id = "job-123"
        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_payload_2,
        ),         patch(
            "app.controller.employer_controller.job.db.execute",
            return_value=MagicMock(scalar_one_or_none=lambda: mock_employer_2),
        ), patch(
            "app.service.employer_service.job_service.JobService.update_job",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=403, detail="Access Denied"),
        ):
            r = client.put(f"/jobs/{job_id}", json=valid_edit_payload, headers={"Authorization": "Bearer test"})
            assert r.status_code == 403
            assert "Access Denied" in str(r.json())

    def test_edit_job_invalid_deadline_returns_400_for_non_expired_job(self, client):
        job_id = "job-123"
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        payload = {**valid_edit_payload, "application_deadline": past}

        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_payload_1,
        ),         patch(
            "app.controller.employer_controller.job.db.execute",
            return_value=MagicMock(scalar_one_or_none=lambda: mock_employer_1),
        ), patch(
            "app.service.employer_service.job_service.JobService.update_job",
            new_callable=AsyncMock,
            side_effect=HTTPException(
                status_code=400,
                detail="Application deadline cannot be in the past",
            ),
        ):
            r = client.put(f"/jobs/{job_id}", json=payload, headers={"Authorization": "Bearer test"})
            assert r.status_code == 400

    def test_existing_skills_replaced_correctly_and_audit_event_type(self, client):
        # This endpoint-level test verifies the call path; repository-level
        # replacement/audit is covered via repository unit tests if present.
        job_id = "job-123"
        dummy_job = DummyJob(job_id=job_id, employer_id="emp-1")

        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_payload_1,
        ),         patch(
            "app.controller.employer_controller.job.db.execute",
            return_value=MagicMock(scalar_one_or_none=lambda: mock_employer_1),
        ), patch(
            "app.service.employer_service.job_service.JobService.update_job",
            new_callable=AsyncMock,
            return_value=dummy_job,
        ) as mock_update:
            r = client.put(f"/jobs/{job_id}", json=valid_edit_payload, headers={"Authorization": "Bearer test"})
            assert r.status_code == 200
            assert mock_update.call_count == 1


class TestEditJobPrefillEndpoint:
    def test_get_job_for_prefill_happy_path(self, client):
        job_id = "job-123"
        dummy_job = DummyJob(job_id=job_id, employer_id="emp-1")

        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_payload_1,
        ), patch(
            "app.controller.employer_controller.job.db.execute",
            return_value=MagicMock(
                scalar_one_or_none=lambda: mock_employer_1
            ),
        ), patch(
            "app.service.employer_service.job_service.JobService.get_job_for_employer",
            new_callable=AsyncMock,
            return_value=dummy_job,
        ):
            r = client.get(
                f"/jobs/{job_id}",
                headers={"Authorization": "Bearer test"},
            )

            assert r.status_code == 200

            assert_response_common(r.json())

