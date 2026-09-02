import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.service.job_application_service import JobApplicationService


def test_apply_for_job_returns_404_when_job_does_not_exist():
    data = SimpleNamespace(
        job_id="JOB_1001",
        resume_id="RES_5001",
        cover_letter_text=None,
        source="NMK Recruitment Portal",
        referral_contact=None,
    )

    with patch(
        "app.service.job_application_service.JobApplicationRepo._get_candidate_id",
        new_callable=AsyncMock,
        return_value="candidate-1",
    ), patch(
        "app.service.job_application_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_job_for_application",
        new_callable=AsyncMock,
        return_value=None,
    ) as get_job, patch(
        "app.service.job_application_service.JobApplicationRepo.application_exists",
        new_callable=AsyncMock,
    ) as application_exists, patch(
        "app.service.job_application_service.JobApplicationRepo.create_application",
        new_callable=AsyncMock,
    ) as create_application:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(JobApplicationService.apply_for_job(None, uuid4(), data))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Job is no longer available."
    get_job.assert_awaited_once()
    application_exists.assert_not_called()
    create_application.assert_not_called()


def test_apply_for_job_returns_404_when_resume_does_not_exist():
    data = SimpleNamespace(
        job_id="job-1",
        resume_id="RESUME_2026_001",
        cover_letter_text=None,
        source="NMK Recruitment Portal",
        referral_contact=None,
    )

    with patch(
        "app.service.job_application_service.JobApplicationRepo._get_candidate_id",
        new_callable=AsyncMock,
        return_value="candidate-1",
    ), patch(
        "app.service.job_application_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_job_for_application",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(status="PUBLISHED", closed_at=None),
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_resume_for_candidate",
        new_callable=AsyncMock,
        return_value=None,
    ) as get_resume, patch(
        "app.service.job_application_service.JobApplicationRepo.application_exists",
        new_callable=AsyncMock,
    ) as application_exists, patch(
        "app.service.job_application_service.JobApplicationRepo.create_application",
        new_callable=AsyncMock,
    ) as create_application:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(JobApplicationService.apply_for_job(None, uuid4(), data))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Resume not found"
    get_resume.assert_awaited_once()
    application_exists.assert_not_called()
    create_application.assert_not_called()


def test_add_note_returns_404_when_application_does_not_exist():
    data = SimpleNamespace(note_text="Follow up next week")

    with patch(
        "app.service.job_application_service.JobApplicationRepo._get_candidate_id",
        new_callable=AsyncMock,
        return_value="candidate-1",
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_application_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.add_note",
        new_callable=AsyncMock,
    ) as add_note:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobApplicationService.add_note(
                    session=None,
                    user_id=uuid4(),
                    application_id="missing-application",
                    data=data,
                )
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Application not found"
    add_note.assert_not_called()


def test_apply_for_job_returns_409_when_job_is_closed():
    data = SimpleNamespace(
        job_id="job-closed",
        resume_id=None,
        cover_letter_text=None,
        source="NMK Recruitment Portal",
        referral_contact=None,
    )

    with patch(
        "app.service.job_application_service.JobApplicationRepo._get_candidate_id",
        new_callable=AsyncMock,
        return_value="candidate-1",
    ), patch(
        "app.service.job_application_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_job_for_application",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(status="CLOSED", closed_at=datetime.now(UTC)),
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.application_exists",
        new_callable=AsyncMock,
    ) as application_exists, patch(
        "app.service.job_application_service.JobApplicationRepo.create_application",
        new_callable=AsyncMock,
    ) as create_application:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(JobApplicationService.apply_for_job(None, uuid4(), data))

    assert exc.value.status_code == 409
    assert exc.value.detail == "This job is no longer accepting applications."
    application_exists.assert_not_called()
    create_application.assert_not_called()


def test_apply_for_job_returns_409_when_deadline_has_passed():
    data = SimpleNamespace(
        job_id="job-expired",
        resume_id=None,
        cover_letter_text=None,
        source="NMK Recruitment Portal",
        referral_contact=None,
    )

    with patch(
        "app.service.job_application_service.JobApplicationRepo._get_candidate_id",
        new_callable=AsyncMock,
        return_value="candidate-1",
    ), patch(
        "app.service.job_application_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_job_for_application",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            status="PUBLISHED",
            closed_at=None,
            application_deadline=datetime(2000, 1, 1),
        ),
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.application_exists",
        new_callable=AsyncMock,
    ) as application_exists, patch(
        "app.service.job_application_service.JobApplicationRepo.create_application",
        new_callable=AsyncMock,
    ) as create_application:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(JobApplicationService.apply_for_job(None, uuid4(), data))

    assert exc.value.status_code == 409
    assert exc.value.detail == "This job is no longer accepting applications."
    application_exists.assert_not_called()
    create_application.assert_not_called()


def test_apply_for_job_notifies_employer_when_application_is_created():
    class FakeSession:
        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def execute(self, *args, **kwargs):
            pass

    user_id = uuid4()
    data = SimpleNamespace(
        job_id="job-1",
        resume_id=None,
        cover_letter_text=None,
        source="NMK Recruitment Portal",
        referral_contact=None,
    )
    job = SimpleNamespace(
        job_id="job-1",
        title="Backend Developer",
        status="PUBLISHED",
        closed_at=None,
        application_deadline=None,
    )
    created = SimpleNamespace(
        application_id="app-1",
        application_status="APPLIED",
    )

    with patch(
        "app.service.job_application_service.JobApplicationRepo._get_candidate_id",
        new_callable=AsyncMock,
        return_value="candidate-1",
    ), patch(
        "app.service.job_application_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_job_for_application",
        new_callable=AsyncMock,
        return_value=job,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.application_exists",
        new_callable=AsyncMock,
        return_value=False,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.create_application",
        new_callable=AsyncMock,
        return_value=created,
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_employer_user_id_for_job",
        new_callable=AsyncMock,
        return_value="employer-user-1",
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.get_candidate_display_name",
        new_callable=AsyncMock,
        return_value="Alice Example",
    ), patch(
        "app.service.job_application_service.NotificationService.create_notification",
        new_callable=AsyncMock,
    ) as create_notification, patch(
        "app.service.job_application_service.ActivityLogService.create_log_for_user_id",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            JobApplicationService.apply_for_job(FakeSession(), user_id, data)
        )

    assert result["application_id"] == "app-1"
    create_notification.assert_awaited_once()
    assert create_notification.await_args.kwargs["recipient_id"] == "employer-user-1"
    assert create_notification.await_args.kwargs["notification_type"] == "APPLICATION_RECEIVED"
    assert create_notification.await_args.kwargs["reference_id"] == "app-1"
    assert create_notification.await_args.kwargs["event_key"] == "application:received:app-1"


def test_withdraw_application_returns_visible_withdrawn_status():
    user_id = uuid4()

    with patch(
        "app.service.job_application_service.JobApplicationRepo._get_candidate_id",
        new_callable=AsyncMock,
        return_value="candidate-1",
    ), patch(
        "app.service.job_application_service.JobApplicationRepo.withdraw_application",
        new_callable=AsyncMock,
        return_value=True,
    ) as withdraw:
        result = asyncio.run(
            JobApplicationService.withdraw_application(
                session=None,
                user_id=user_id,
                application_id="app-1",
            )
        )

    assert result["message"] == "Application withdrawn successfully"
    assert result["application_status"] == "WITHDRAWN"
    withdraw.assert_awaited_once_with(
        session=None,
        application_id="app-1",
        candidate_id="candidate-1",
        changed_by=user_id,
    )
