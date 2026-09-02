from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.repository.candidate_repo import CandidateProfileRepo
from app.repository.employer_repository.job_repo import JobRepository
from app.repository.employer_repository.interview_repo import InterviewRepo
from app.repository.employer_repository.shortlisted_candidates_repo import (
    ShortlistedCandidatesRepo,
)
from app.schema.job import JobListFiltersSchema
from app.service.employer_service.job_service import JobService


recruiter_payload = {
    "user_id": "user-1",
    "jti": "jwt-1",
    "email": "recruiter@example.com",
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
    botocore_module = types.ModuleType("botocore")
    botocore_exceptions_module = types.ModuleType("botocore.exceptions")
    botocore_exceptions_module.ClientError = Exception
    sys.modules.setdefault("botocore", botocore_module)
    sys.modules.setdefault("botocore.exceptions", botocore_exceptions_module)

    from app.main import init_app

    return TestClient(init_app())


def test_delete_job_endpoint_success(client):
    employer = SimpleNamespace(id="emp-1")

    with patch(
        "app.repository.authentication.auth_repo.JWTRepo.extract_token",
        return_value=recruiter_payload,
    ), patch(
        "app.dependencies.auth_dependencies.UserSessionRepository.find_active_session_by_jwt_id",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(user_id="user-1"),
    ), patch(
        "app.dependencies.auth_dependencies.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(deleted_flag=False, user_status="ACTIVE"),
    ), patch(
        "app.controller.employer_controller.job.db.execute",
        return_value=MagicMock(scalar_one_or_none=lambda: employer),
    ), patch(
        "app.controller.employer_controller.job.delete_job_service",
        new_callable=AsyncMock,
        return_value={"success": True, "message": "Job deleted successfully."},
    ) as delete_job_service:
        response = client.delete(
            "/jobs/job-1",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": 200,
        "message": "Job deleted successfully.",
    }
    delete_job_service.assert_awaited_once()


def test_delete_job_service_invalid_job_returns_404():
    with patch(
        "app.service.employer_service.job_service.JobRepository.delete_job",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Job not found."),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobService.delete_job(
                    session=None,
                    employer_id="emp-1",
                    job_id="missing",
                    actor_user_id="user-1",
                    actor_email="recruiter@example.com",
                )
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Job not found."


def test_delete_job_service_other_employer_returns_403():
    with patch(
        "app.service.employer_service.job_service.JobRepository.delete_job",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=403,
            detail="You are not authorized to delete this job.",
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobService.delete_job(
                    session=None,
                    employer_id="emp-2",
                    job_id="job-1",
                    actor_user_id="user-2",
                    actor_email="other@example.com",
                )
            )

    assert exc.value.status_code == 403
    assert exc.value.detail == "You are not authorized to delete this job."


def test_delete_job_service_integrity_error_returns_controlled_conflict():
    class _RollbackOnlySession:
        def __init__(self):
            self.rolled_back = False

        async def rollback(self):
            self.rolled_back = True

    session = _RollbackOnlySession()
    with patch(
        "app.service.employer_service.job_service.JobRepository.delete_job",
        new_callable=AsyncMock,
        side_effect=IntegrityError("soft delete failed", {}, Exception("fk")),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobService.delete_job(
                    session=session,
                    employer_id="emp-1",
                    job_id="job-1",
                    actor_user_id="user-1",
                    actor_email="recruiter@example.com",
                )
            )

    assert exc.value.status_code == 409
    assert exc.value.detail == (
        "Job could not be deleted because related records are still being processed."
    )
    assert session.rolled_back is True


def test_repeated_delete_request_returns_404_after_first_success():
    activity_log = AsyncMock(return_value=None)
    with patch(
        "app.service.employer_service.job_service.JobRepository.delete_job",
        new_callable=AsyncMock,
        side_effect=[
            True,
            HTTPException(status_code=404, detail="Job not found."),
        ],
    ) as delete_job, patch(
        "app.service.employer_service.job_service.ActivityLogService.create_log_for_user_id",
        activity_log,
    ):
        first = asyncio.run(
            JobService.delete_job(
                session=None,
                employer_id="emp-1",
                job_id="job-1",
                actor_user_id="user-1",
                actor_email="recruiter@example.com",
            )
        )
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobService.delete_job(
                    session=None,
                    employer_id="emp-1",
                    job_id="job-1",
                    actor_user_id="user-1",
                    actor_email="recruiter@example.com",
                )
            )

    assert first == {"success": True, "message": "Job deleted successfully."}
    assert exc.value.status_code == 404
    assert delete_job.await_args_list[0].kwargs["commit"] is False
    assert activity_log.await_count == 1


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def all(self):
        return self.value or []

    def scalars(self):
        return self


class _FakeSession:
    def __init__(self, job=None, fail_on_commit=False):
        self.job = job
        self.fail_on_commit = fail_on_commit
        self.added = []
        self.operations = []
        self.committed = False
        self.flushed = False
        self.rolled_back = False
        self._execute_count = 0

    def add(self, value):
        self.added.append(value)

    async def execute(self, statement):
        self._execute_count += 1
        if self._execute_count == 1:
            return _Result(self.job)

        return _Result(None)

    async def commit(self):
        if self.fail_on_commit:
            raise RuntimeError("soft delete commit failed")
        self.committed = True

    async def flush(self):
        if self.fail_on_commit:
            raise RuntimeError("soft delete flush failed")
        self.flushed = True

    async def rollback(self):
        self.rolled_back = True


class _RecordingSession:
    def __init__(self, scalar=None, rows=None):
        self.scalar = scalar
        self.rows = rows or []
        self.statements = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _Result(self.scalar)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _combined_sql(session) -> str:
    return "\n".join(session.statements).lower()


def test_delete_job_repository_soft_deletes_job_without_removing_history():
    job = SimpleNamespace(
        job_id="job-1",
        employer_id="emp-1",
        title="Engineer",
        status="PUBLISHED",
        is_deleted=False,
        deleted_at=None,
        closed_at=None,
        closed_reason=None,
        updated_at=None,
        updated_by=None,
    )
    session = _FakeSession(job=job)

    result = asyncio.run(
        JobRepository.delete_job(
            job_id="job-1",
            employer_id="emp-1",
            db=session,
            actor_user_id="user-1",
            actor_email="recruiter@example.com",
        )
    )

    assert result is True
    assert session.committed is True
    assert session.flushed is False
    assert session.rolled_back is False

    assert session.added[0].event_type == "JOB_DELETED"
    assert session.added[0].job_id == "job-1"
    assert "deleted_job_id=job-1" in session.added[0].message
    assert "previous_status=PUBLISHED" in session.added[0].message
    assert job.is_deleted is True
    assert job.deleted_at is not None
    assert job.status == "CLOSED"
    assert job.closed_at == job.deleted_at
    assert job.closed_reason == "Deleted by employer"
    assert job.updated_by == "user-1"
    assert session.operations == []


def test_delete_job_repository_rolls_back_if_soft_delete_commit_fails():
    job = SimpleNamespace(
        job_id="job-1",
        employer_id="emp-1",
        title="Engineer",
        status="PUBLISHED",
        is_deleted=False,
        deleted_at=None,
        closed_at=None,
        closed_reason=None,
        updated_at=None,
        updated_by=None,
    )
    session = _FakeSession(job=job, fail_on_commit=True)

    with pytest.raises(RuntimeError):
        asyncio.run(
            JobRepository.delete_job(
                job_id="job-1",
                employer_id="emp-1",
                db=session,
                actor_user_id="user-1",
                actor_email="recruiter@example.com",
            )
        )

    assert session.committed is False
    assert session.rolled_back is True
    assert ("Delete", "jobs") not in session.operations


def test_delete_job_repository_can_flush_for_service_level_transaction():
    job = SimpleNamespace(
        job_id="job-1",
        employer_id="emp-1",
        title="Engineer",
        status="PUBLISHED",
        is_deleted=False,
        deleted_at=None,
        closed_at=None,
        closed_reason=None,
        updated_at=None,
        updated_by=None,
    )
    session = _FakeSession(job=job)

    result = asyncio.run(
        JobRepository.delete_job(
            job_id="job-1",
            employer_id="emp-1",
            db=session,
            actor_user_id="user-1",
            actor_email="recruiter@example.com",
            commit=False,
        )
    )

    assert result is True
    assert session.flushed is True
    assert session.committed is False
    assert job.is_deleted is True


def test_employer_manage_jobs_query_excludes_deleted_jobs():
    session = _RecordingSession(rows=[])

    rows, total = asyncio.run(
        JobRepository.list_employer_jobs(
            session=session,
            employer_id="emp-1",
            filters=JobListFiltersSchema(page=1, page_size=20),
        )
    )

    sql = _combined_sql(session)
    assert total == 0
    assert rows == []
    assert "jobs.is_deleted" in sql


def test_employer_job_details_query_excludes_deleted_jobs():
    session = _RecordingSession()

    result = asyncio.run(
        JobRepository.get_job_for_employer(
            session=session,
            employer_id="emp-1",
            job_id="job-1",
        )
    )

    assert result is None
    sql = _combined_sql(session)
    assert "jobs.is_deleted" in sql


def test_candidate_save_deleted_job_returns_unavailable_without_creating_saved_row():
    session = _RecordingSession()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            CandidateProfileRepo.save_job(
                session=session,
                candidate_id="candidate-1",
                job_id="job-1",
            )
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Job is no longer available."
    assert session.committed is False
    assert len(session.statements) == 1


def test_shortlisting_application_for_deleted_job_is_not_found():
    session = _RecordingSession()

    result = asyncio.run(
        ShortlistedCandidatesRepo.get_application_for_employer(
            session=session,
            employer_id="emp-1",
            application_id="app-1",
        )
    )

    assert result is None
    assert "jobs.is_deleted" in _combined_sql(session)


def test_interview_lookup_for_deleted_job_is_not_found():
    session = _RecordingSession()

    result = asyncio.run(
        InterviewRepo.get_by_id_for_employer(
            session=session,
            employer_id="emp-1",
            interview_id="interview-1",
        )
    )

    assert result is None
    assert "jobs.is_deleted" in _combined_sql(session)
