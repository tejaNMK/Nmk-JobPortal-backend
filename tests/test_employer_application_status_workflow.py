import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.service.employer_service.job_applicants_service import JobApplicantsService


def _application(status: str = "REJECTED"):
    return SimpleNamespace(
        application_id="app-1",
        job_id="job-1",
        candidate_id="candidate-1",
        application_status=status,
        updated_at=datetime(2026, 8, 17, 10, 0, 0),
        shortlisted_at=None,
    )


def test_employer_restores_rejected_application_to_shortlisted():
    user_id = uuid4()
    app = _application("REJECTED")
    updated = _application("SHORTLISTED")

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_application",
        new_callable=AsyncMock,
        return_value=app,
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.update_application_status",
        new_callable=AsyncMock,
        return_value=updated,
    ) as update_status:
        result = asyncio.run(
            JobApplicantsService.update_application_status(
                session=SimpleNamespace(),
                user_id=user_id,
                application_id="app-1",
                payload=SimpleNamespace(status="SHORTLISTED", reason="Rehire"),
            )
        )

    assert result.application_id == "app-1"
    assert result.job_id == "job-1"
    assert result.candidate_id == "candidate-1"
    assert result.previous_status == "REJECTED"
    assert result.application_status == "SHORTLISTED"
    update_status.assert_awaited_once()
    assert update_status.await_args.kwargs["reason"] == "Rehire"


def test_repeated_status_update_is_idempotent():
    user_id = uuid4()
    app = _application("SHORTLISTED")

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_application",
        new_callable=AsyncMock,
        return_value=app,
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.update_application_status",
        new_callable=AsyncMock,
    ) as update_status:
        result = asyncio.run(
            JobApplicantsService.update_application_status(
                session=SimpleNamespace(),
                user_id=user_id,
                application_id="app-1",
                payload=SimpleNamespace(status="SHORTLISTED", reason=None),
            )
        )

    assert result.previous_status == "SHORTLISTED"
    assert result.application_status == "SHORTLISTED"
    update_status.assert_not_awaited()


def test_another_employer_cannot_update_application():
    user_id = uuid4()

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-2",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_application",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_application_by_id",
        new_callable=AsyncMock,
        return_value=_application("SHORTLISTED"),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobApplicantsService.update_application_status(
                    session=SimpleNamespace(),
                    user_id=user_id,
                    application_id="app-1",
                    payload=SimpleNamespace(status="REJECTED", reason=None),
                )
            )

    assert exc.value.status_code == 403


def test_missing_application_returns_404():
    user_id = uuid4()

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_application",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_application_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobApplicantsService.update_application_status(
                    session=SimpleNamespace(),
                    user_id=user_id,
                    application_id="missing",
                    payload=SimpleNamespace(status="REJECTED", reason=None),
                )
            )

    assert exc.value.status_code == 404


def test_invalid_transition_returns_400():
    user_id = uuid4()
    app = _application("ARCHIVED")

    with patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.job_applicants_service."
        "JobApplicantsRepo.get_employer_application",
        new_callable=AsyncMock,
        return_value=app,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                JobApplicantsService.update_application_status(
                    session=SimpleNamespace(),
                    user_id=user_id,
                    application_id="app-1",
                    payload=SimpleNamespace(status="REJECTED", reason=None),
                )
            )

    assert exc.value.status_code == 400
