import asyncio
import sys
import types
from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

boto3_stub = types.ModuleType("boto3")
boto3_stub.client = lambda *args, **kwargs: SimpleNamespace()
botocore_stub = types.ModuleType("botocore")
botocore_exceptions_stub = types.ModuleType("botocore.exceptions")
botocore_exceptions_stub.ClientError = Exception
botocore_exceptions_stub.BotoCoreError = Exception
botocore_exceptions_stub.EndpointConnectionError = Exception
sys.modules.setdefault("boto3", boto3_stub)
sys.modules.setdefault("botocore", botocore_stub)
sys.modules.setdefault("botocore.exceptions", botocore_exceptions_stub)

from app.config import get_db
from app.dependencies.role_dependencies import employer_user_only
from app.main import init_app
from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.model.employer_model.interview import Interview
from app.model.employer_model.interviewer import Interviewer
from app.schema.interview import (
    InterviewMode,
    InterviewerCreateRequest,
    InterviewerPayload,
    InterviewerUpdateRequest,
    ScheduleInterviewRequest,
)
from app.service.employer_service.interview_service import (
    InterviewService,
    InterviewerService,
)


bootstrap_mappers()


def _session():
    return SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        refresh=AsyncMock(),
        add=lambda value: None,
    )


def _interviewer(**overrides):
    data = {
        "id": "int-1",
        "name": "Priya Sharma",
        "email": "priya@example.com",
    }
    data.update(overrides)
    return Interviewer(**data)


def _request(**overrides):
    data = {
        "interview_round": "HR Discussion",
        "interview_title": "Backend Interview",
        "round_number": 1,
        "interview_date": date.today() + timedelta(days=1),
        "interview_time": time(10, 30),
        "start_time": time(10, 30),
        "end_time": time(11, 30),
        "timezone": "Asia/Kolkata",
        "mode": InterviewMode.ONLINE,
        "meeting_link": "https://meet.example.com/abc",
        "interviewers": [
            {"name": "Priya Sharma", "email": "PRIYA@EXAMPLE.COM"}
        ],
    }
    data.update(overrides)
    return ScheduleInterviewRequest(**data)


def _interview(**overrides):
    data = {
        "application_id": "app-1",
        "interview_title": "Backend Interview",
        "round_number": 1,
        "interview_round": "HR Round",
        "interview_date": date.today() + timedelta(days=1),
        "interview_time": time(10, 30),
        "end_time": time(11, 30),
        "timezone": "Asia/Kolkata",
        "mode": "ONLINE",
        "meeting_link": "https://meet.example.com/abc",
        "status": "SCHEDULED",
    }
    data.update(overrides)
    return Interview(**data)


def _email_details():
    return (
        "Asha",
        "Rao",
        "asha@example.com",
        "candidate-user-1",
        "candidate-1",
        "NMK Global",
        "hr@example.com",
        "employer-user-1",
        "Backend Engineer",
        "resume-1",
    )


def test_create_interviewer_normalizes_email_and_name():
    session = _session()

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_email",
        new_callable=AsyncMock,
        return_value=None,
    ) as get_by_email, patch(
        "app.service.employer_service.interview_service.InterviewerRepo.create",
        new_callable=AsyncMock,
        side_effect=lambda session, interviewer: interviewer,
    ):
        result = asyncio.run(
            InterviewerService.create_interviewer(
                session=session,
                request=InterviewerCreateRequest(
                    name="  Priya   Sharma  ",
                    email="PRIYA@EXAMPLE.COM",
                ),
            )
        )

    get_by_email.assert_awaited_once_with(
        session=session,
        email="priya@example.com",
    )
    assert result.name == "Priya Sharma"
    assert result.email == "priya@example.com"
    session.commit.assert_awaited_once()


def test_create_interviewer_rejects_invalid_email():
    with pytest.raises(ValidationError):
        InterviewerCreateRequest(name="Priya", email="not-an-email")


def test_create_interviewer_rejects_duplicate_normalized_email():
    session = _session()

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_email",
        new_callable=AsyncMock,
        return_value=_interviewer(),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                InterviewerService.create_interviewer(
                    session=session,
                    request=InterviewerCreateRequest(
                        name="Priya",
                        email="PRIYA@EXAMPLE.COM",
                    ),
                )
            )

    assert exc.value.status_code == 409


def test_update_interviewer():
    session = _session()
    interviewer = _interviewer()

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_id",
        new_callable=AsyncMock,
        return_value=interviewer,
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_email",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = asyncio.run(
            InterviewerService.update_interviewer(
                session=session,
                interviewer_id="int-1",
                request=InterviewerUpdateRequest(
                    name="John Smith",
                    email="JOHN@EXAMPLE.COM",
                ),
            )
        )

    assert result.name == "John Smith"
    assert result.email == "john@example.com"
    session.commit.assert_awaited_once()


def test_delete_interviewer():
    session = _session()

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_id",
        new_callable=AsyncMock,
        return_value=_interviewer(),
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.count_interview_assignments",
        new_callable=AsyncMock,
        return_value=0,
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.delete",
        new_callable=AsyncMock,
    ) as delete:
        asyncio.run(
            InterviewerService.delete_interviewer(
                session=session,
                interviewer_id="int-1",
            )
        )

    delete.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_delete_assigned_interviewer_returns_conflict():
    session = _session()

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_id",
        new_callable=AsyncMock,
        return_value=_interviewer(),
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.count_interview_assignments",
        new_callable=AsyncMock,
        return_value=2,
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.delete",
        new_callable=AsyncMock,
    ) as delete:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                InterviewerService.delete_interviewer(
                    session=session,
                    interviewer_id="int-1",
                )
            )

    assert exc.value.status_code == 409
    assert exc.value.detail == (
        "This interviewer is assigned to one or more interviews. Remove the "
        "interviewer from those interviews before deleting."
    )
    delete.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_delete_interviewer_not_found():
    session = _session()

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.count_interview_assignments",
        new_callable=AsyncMock,
    ) as count_assignments, patch(
        "app.service.employer_service.interview_service.InterviewerRepo.delete",
        new_callable=AsyncMock,
    ) as delete:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                InterviewerService.delete_interviewer(
                    session=session,
                    interviewer_id="missing",
                )
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Interviewer not found."
    count_assignments.assert_not_awaited()
    delete.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_delete_interviewer_rolls_back_on_integrity_error():
    session = _session()

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_id",
        new_callable=AsyncMock,
        return_value=_interviewer(),
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.count_interview_assignments",
        new_callable=AsyncMock,
        return_value=0,
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.delete",
        new_callable=AsyncMock,
        side_effect=IntegrityError("delete failed", params=None, orig=Exception()),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                InterviewerService.delete_interviewer(
                    session=session,
                    interviewer_id="int-1",
                )
            )

    assert exc.value.status_code == 409
    assert exc.value.detail == (
        "This interviewer is assigned to one or more interviews. Remove the "
        "interviewer from those interviews before deleting."
    )
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_delete_interviewer_rejects_unauthorized_user():
    app = init_app()

    async def fake_db():
        yield SimpleNamespace()

    async def unauthorized_user():
        raise HTTPException(
            status_code=403,
            detail="Only employers can access this resource",
        )

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[employer_user_only] = unauthorized_user

    with patch(
        "app.controller.employer_controller.interviewers.InterviewerService.delete_interviewer",
        new_callable=AsyncMock,
    ) as delete_interviewer:
        response = TestClient(app).delete("/employer/interviewers/int-1")

    assert response.status_code == 403
    assert response.json()["message"] == "Only employers can access this resource"
    delete_interviewer.assert_not_awaited()


@pytest.mark.parametrize("search", ["Priya", "priya@example.com"])
def test_search_interviewers_by_name_or_email(search):
    session = SimpleNamespace()

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.list",
        new_callable=AsyncMock,
        return_value=(1, [_interviewer()]),
    ) as list_interviewers:
        result = asyncio.run(
            InterviewerService.list_interviewers(
                session=session,
                search=search,
                page=1,
                page_size=20,
            )
        )

    list_interviewers.assert_awaited_once_with(
        session=session,
        search=search,
        page=1,
        page_size=20,
    )
    assert result.total == 1
    assert result.items[0].email == "priya@example.com"


def test_scheduling_auto_creates_and_assigns_external_interviewer():
    session = _session()
    created = _interviewer(id="int-new")

    with patch(
        "app.service.employer_service.interview_service.ShortlistedCandidatesRepo.get_application_for_employer",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(application_status="SHORTLISTED"),
    ), patch(
        "app.service.employer_service.interview_service.InterviewRepo.get_duplicate_interview",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.create",
        new_callable=AsyncMock,
        return_value=created,
    ) as create_interviewer, patch(
        "app.service.employer_service.interview_service.InterviewRepo.create_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview, **kwargs: interview,
    ), patch(
        "app.service.employer_service.interview_service.ShortlistedCandidatesRepo.update_status",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service.InterviewInterviewerRepo.replace_interviewers",
        new_callable=AsyncMock,
        return_value=({"int-new"}, set()),
    ) as replace_interviewers, patch(
        "app.service.employer_service.interview_service.InterviewInterviewerRepo.get_assigned_interviewers",
        new_callable=AsyncMock,
        return_value=[("int-new", "Priya Sharma", "priya@example.com")],
    ), patch(
        "app.service.employer_service.interview_service.InterviewRepo.update_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview, **kwargs: interview,
    ), patch(
        "app.service.employer_service.interview_service.InterviewHistoryRepo.create_history",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service.ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=_email_details(),
    ), patch(
        "app.service.employer_service.interview_service.InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[("int-new", "Priya Sharma", "priya@example.com")],
    ), patch(
        "app.service.employer_service.interview_service.EmailService.send_interview_scheduled_email",
        new_callable=AsyncMock,
    ) as send_email, patch(
        "app.service.employer_service.interview_service.InterviewService._get_resume_attachment",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service.NotificationService.create_notification",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            InterviewService.schedule_interview(
                session=session,
                employer_id="emp-1",
                application_id="app-1",
                request=_request(),
                performed_by="user-1",
            )
        )

    create_interviewer.assert_awaited_once()
    replace_interviewers.assert_awaited_once()
    assert result.assigned_interviewers[0].email == "priya@example.com"
    assert send_email.await_count == 2
    session.commit.assert_awaited_once()


def test_scheduling_reuses_existing_interviewer_by_email_and_deduplicates_request():
    session = _session()
    existing = _interviewer(id="int-existing")
    request = _request(
        interviewers=[
            {"name": "Priya Sharma", "email": "PRIYA@EXAMPLE.COM"},
            {"name": "Priya Sharma", "email": "priya@example.com"},
        ]
    )

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_emails",
        new_callable=AsyncMock,
        return_value=[existing],
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.create",
        new_callable=AsyncMock,
    ) as create_interviewer:
        ids = asyncio.run(
            InterviewService._resolve_interviewers(
                session=session,
                interviewer_ids=None,
                interviewer_emails=None,
                interviewers=request.interviewers,
            )
        )

    assert ids == ["int-existing"]
    create_interviewer.assert_not_awaited()


def test_multiple_external_interviewers_are_created():
    session = _session()
    created = [
        _interviewer(id="int-1", name="John Smith", email="john@example.com"),
        _interviewer(id="int-2", name="Priya Sharma", email="priya@example.com"),
    ]

    with patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.create",
        new_callable=AsyncMock,
        side_effect=created,
    ):
        ids = asyncio.run(
            InterviewService._resolve_interviewers(
                session=session,
                interviewer_ids=None,
                interviewer_emails=None,
                interviewers=[
                    InterviewerPayload(name="John Smith", email="john@example.com"),
                    InterviewerPayload(name="Priya Sharma", email="priya@example.com"),
                ],
            )
        )

    assert ids == ["int-1", "int-2"]


def test_rescheduling_adds_and_removes_interviewers():
    session = _session()
    interview = _interview()

    with patch(
        "app.service.employer_service.interview_service.InterviewInterviewerRepo.replace_interviewers",
        new_callable=AsyncMock,
        return_value=({"int-2"}, {"int-1"}),
    ) as replace_interviewers, patch(
        "app.service.employer_service.interview_service.InterviewInterviewerRepo.get_assigned_interviewers",
        new_callable=AsyncMock,
        return_value=[("int-2", "John Smith", "john@example.com")],
    ), patch(
        "app.service.employer_service.interview_service.InterviewRepo.update_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview, **kwargs: interview,
    ):
        asyncio.run(
            InterviewService._replace_interviewers(
                session=session,
                interview=interview,
                interviewer_ids=["int-2"],
            )
        )

    replace_interviewers.assert_awaited_once()
    assert interview.interviewer_name == "John Smith"


def test_transaction_rollback_prevents_email_notification():
    session = _session()

    with patch(
        "app.service.employer_service.interview_service.ShortlistedCandidatesRepo.get_application_for_employer",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(application_status="SHORTLISTED"),
    ), patch(
        "app.service.employer_service.interview_service.InterviewRepo.get_duplicate_interview",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service.InterviewerRepo.get_by_emails",
        new_callable=AsyncMock,
        return_value=[_interviewer(id="int-1")],
    ), patch(
        "app.service.employer_service.interview_service.InterviewRepo.create_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview, **kwargs: interview,
    ), patch(
        "app.service.employer_service.interview_service.ShortlistedCandidatesRepo.update_status",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service.InterviewInterviewerRepo.replace_interviewers",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db failed"),
    ), patch(
        "app.service.employer_service.interview_service.EmailService.send_interview_scheduled_email",
        new_callable=AsyncMock,
    ) as send_email:
        with pytest.raises(RuntimeError):
            asyncio.run(
                InterviewService.schedule_interview(
                    session=session,
                    employer_id="emp-1",
                    application_id="app-1",
                    request=_request(),
                )
            )

    session.rollback.assert_awaited_once()
    send_email.assert_not_awaited()
