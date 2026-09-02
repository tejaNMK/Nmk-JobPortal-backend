import asyncio
from datetime import date, timedelta, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.model.employer_model.interview import Interview
from app.schema.interview import (
    InterviewMode,
    ScheduleInterviewRoundsRequest,
    ScheduleInterviewRequest,
)
from app.repository.employer_repository.interview_repo import InterviewRepo
from app.service.employer_service.interview_service import InterviewService


bootstrap_mappers()


def _request(**overrides):
    data = {
        "interview_round": SimpleNamespace(value="HR Round"),
        "interview_title": "Backend Interview",
        "round_number": 1,
        "interview_date": date.today() + timedelta(days=1),
        "interview_time": time(10, 30),
        "start_time": time(10, 30),
        "end_time": time(11, 30),
        "timezone": "Asia/Kolkata",
        "mode": SimpleNamespace(value="ONLINE"),
        "meeting_link": "https://meet.example.com/abc",
        "interview_location": None,
        "interviewer_name": "Priya Recruiter",
        "interviewer_ids": None,
        "remarks": "Bring portfolio",
        "status": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


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
        "interview_location": None,
        "interviewer_name": "Priya Recruiter",
        "remarks": "Bring portfolio",
        "status": "SCHEDULED",
    }
    data.update(overrides)
    return Interview(**data)


def _email_details(employer_email=None):
    return (
        "Asha",
        "Rao",
        "asha@example.com",
        uuid4(),
        "candidate-1",
        "NMK Global",
        employer_email,
        uuid4(),
        "Backend Engineer",
        "resume-1",
    )


def test_schedule_interview_sends_email_and_records_history():
    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_application_for_employer",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(application_status="SHORTLISTED"),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_duplicate_interview",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.create_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview: interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.update_status",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewHistoryRepo.create_history",
        new_callable=AsyncMock,
    ) as create_history, patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=_email_details(),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service."
        "NotificationService.create_notification",
        new_callable=AsyncMock,
    ),patch(
        "app.service.employer_service.interview_service."
        "EmailService.send_interview_scheduled_email",
        new_callable=AsyncMock,
    ) as send_email:
        result = asyncio.run(
            InterviewService.schedule_interview(
                session=None,
                employer_id="emp-1",
                application_id="app-1",
                request=_request(),
                performed_by="user-1",
            )
        )

    assert result.status == "SCHEDULED"
    create_history.assert_awaited_once()
    send_email.assert_awaited_once()


def test_reschedule_interview_sends_rescheduled_email():
    interview = _interview()

    with patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_by_id_for_employer",
        new_callable=AsyncMock,
        return_value=interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_duplicate_interview",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.update_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview: interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewHistoryRepo.create_history",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=_email_details(),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service."
        "NotificationService.create_notification",
        new_callable=AsyncMock,
    ),patch(
        "app.service.employer_service.interview_service."
        "EmailService.send_interview_rescheduled_email",
        new_callable=AsyncMock,
    ) as send_email:
        result = asyncio.run(
            InterviewService.update_interview(
                session=None,
                employer_id="emp-1",
                interview_id=interview.interview_id,
                request=_request(
                    interview_date=date.today() + timedelta(days=2)
                ),
                performed_by="user-1",
            )
        )

    assert result.status == "RESCHEDULED"
    send_email.assert_awaited_once()


def test_cancel_interview_sends_cancelled_email():
    interview = _interview()

    with patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_by_id_for_employer",
        new_callable=AsyncMock,
        return_value=interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.update_status",
        new_callable=AsyncMock,
        side_effect=lambda session, interview, status: setattr(
            interview, "status", status
        ) or interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewHistoryRepo.create_history",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=_email_details(),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service."
        "NotificationService.create_notification",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "EmailService.send_interview_cancelled_email",
        new_callable=AsyncMock,
    ) as send_email:
        result = asyncio.run(
            InterviewService.cancel_interview(
                session=None,
                employer_id="emp-1",
                interview_id=interview.interview_id,
                performed_by="user-1",
            )
        )

    assert result.status == "CANCELLED"
    send_email.assert_awaited_once()


def test_complete_interview_records_completed_status():
    interview = _interview()

    with patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_by_id_for_employer",
        new_callable=AsyncMock,
        return_value=interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.update_status",
        new_callable=AsyncMock,
        side_effect=lambda session, interview, status: setattr(
            interview, "status", status
        ) or interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewHistoryRepo.create_history",
        new_callable=AsyncMock,
    ) as create_history:
        result = asyncio.run(
            InterviewService.complete_interview(
                session=None,
                employer_id="emp-1",
                interview_id=interview.interview_id,
                performed_by="user-1",
            )
        )

    assert result.status == "COMPLETED"
    create_history.assert_awaited_once()


def test_mark_no_show_records_no_show_status():
    interview = _interview()

    with patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_by_id_for_employer",
        new_callable=AsyncMock,
        return_value=interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.update_status",
        new_callable=AsyncMock,
        side_effect=lambda session, interview, status: setattr(
            interview, "status", status
        ) or interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewHistoryRepo.create_history",
        new_callable=AsyncMock,
    ) as create_history:
        result = asyncio.run(
            InterviewService.mark_no_show(
                session=None,
                employer_id="emp-1",
                interview_id=interview.interview_id,
                performed_by="user-1",
            )
        )

    assert result.status == "NO_SHOW"
    create_history.assert_awaited_once()


def test_schedule_interview_rejects_unauthorized_employer():
    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_application_for_employer",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                InterviewService.schedule_interview(
                    session=None,
                    employer_id="emp-1",
                    application_id="app-1",
                    request=_request(),
                )
            )

    assert exc.value.status_code == 403


def test_schedule_interview_rejects_duplicate_round_or_timeslot():
    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_application_for_employer",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(application_status="SHORTLISTED"),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_duplicate_interview",
        new_callable=AsyncMock,
        return_value=_interview(),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                InterviewService.schedule_interview(
                    session=None,
                    employer_id="emp-1",
                    application_id="app-1",
                    request=_request(),
                )
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == (
        "An interview already exists for the selected date and time."
    )


def test_past_date_validation():
    with pytest.raises(ValidationError):
        ScheduleInterviewRequest(
            interview_round="HR Discussion",
            interview_date=date.today() - timedelta(days=1),
            interview_time=time(10, 30),
            end_time=time(11, 30),
            mode=InterviewMode.ONLINE,
            meeting_link="https://meet.example.com/abc",
            interviewer_ids=[uuid4()],
        )


def test_online_validation_requires_meeting_link():
    with pytest.raises(ValidationError):
        ScheduleInterviewRequest(
            interview_round="HR Discussion",
            interview_date=date.today() + timedelta(days=1),
            interview_time=time(10, 30),
            end_time=time(11, 30),
            mode=InterviewMode.ONLINE,
            interviewer_ids=[uuid4()],
        )


def test_offline_validation_requires_location():
    with pytest.raises(ValidationError):
        ScheduleInterviewRequest(
            interview_round="HR Discussion",
            interview_date=date.today() + timedelta(days=1),
            interview_time=time(10, 30),
            end_time=time(11, 30),
            mode=InterviewMode.OFFLINE,
            interviewer_ids=[uuid4()],
        )


def test_email_failure_does_not_fail_scheduling():
    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_application_for_employer",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(application_status="SHORTLISTED"),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_duplicate_interview",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.create_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview: interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.update_status",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewHistoryRepo.create_history",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=_email_details(),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service."
        "NotificationService.create_notification",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "EmailService.send_interview_scheduled_email",
        new_callable=AsyncMock,
        side_effect=RuntimeError("smtp down"),
    ):
        result = asyncio.run(
            InterviewService.schedule_interview(
                session=None,
                employer_id="emp-1",
                application_id="app-1",
                request=_request(),
            )
        )

    assert result.status == "SCHEDULED"


def test_schedule_request_rejects_duplicate_interviewers():
    interviewer_id = uuid4()

    with pytest.raises(ValidationError):
        ScheduleInterviewRequest(
            interview_round="HR Discussion",
            interview_date=date.today() + timedelta(days=1),
            interview_time=time(10, 30),
            end_time=time(11, 30),
            mode=InterviewMode.ONLINE,
            meeting_link="https://meet.example.com/abc",
            interviewer_ids=[interviewer_id, interviewer_id],
        )


def test_schedule_rounds_request_rejects_duplicate_round_numbers():
    interviewer_one = uuid4()
    interviewer_two = uuid4()

    with pytest.raises(ValidationError):
        ScheduleInterviewRoundsRequest(
            rounds=[
                ScheduleInterviewRequest(
                    round_number=1,
                    interview_round="HR Discussion",
                    interview_date=date.today() + timedelta(days=1),
                    interview_time=time(10, 30),
                    end_time=time(11, 30),
                    mode=InterviewMode.ONLINE,
                    meeting_link="https://meet.example.com/abc",
                    interviewer_ids=[interviewer_one],
                ),
                ScheduleInterviewRequest(
                    round_number=1,
                    interview_round="Technical Round",
                    interview_date=date.today() + timedelta(days=2),
                    interview_time=time(12, 30),
                    end_time=time(13, 30),
                    mode=InterviewMode.ONLINE,
                    meeting_link="https://meet.example.com/def",
                    interviewer_ids=[interviewer_two],
                ),
            ]
        )


def test_ics_attachment_includes_calendar_fields():
    interview = _interview()
    payload = InterviewService._build_interview_email_payload(
        candidate_name="Asha Rao",
        company_name="NMK Global",
        employer_name="NMK Global",
        job_title="Backend Engineer",
        interview=interview,
    )

    attachment = InterviewService._build_ics_attachment(
        payload=payload,
        interview=interview,
        organizer="hr@example.com",
        attendees=["asha@example.com", "interviewer@example.com"],
    )

    assert attachment is not None
    filename, content, content_type = attachment
    calendar = content.decode("utf-8")
    assert filename == "interview-invite.ics"
    assert content_type == "text/calendar"
    assert "BEGIN:VCALENDAR" in calendar
    assert "SUMMARY:Backend Interview" in calendar
    assert "ATTENDEE:MAILTO:interviewer@example.com" in calendar


def test_interview_notifications_attach_application_resume_to_candidate_only():
    interview = _interview()
    resume_attachment = (
        "resume.pdf",
        b"resume-bytes",
        "application/pdf",
    )

    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=_email_details("hr@example.com"),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[
            (uuid4(), "Priya", "Recruiter", "priya@example.com"),
            (uuid4(), "Neel", "Manager", "neel@example.com"),
        ],
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewService._get_resume_attachment",
        new_callable=AsyncMock,
        return_value=resume_attachment,
    ), patch(
        "app.service.employer_service.interview_service."
        "EmailService.send_interview_scheduled_email",
        new_callable=AsyncMock,
    ) as send_email, patch(
        "app.service.employer_service.interview_service."
        "NotificationService.create_notification",
        new_callable=AsyncMock,
    ) as create_notification:
        result = asyncio.run(
            InterviewService._send_interview_notifications(
                session=None,
                application_id="app-1",
                interview=interview,
                email_sender=send_email,
            )
        )

    assert send_email.await_count == 3
    candidate_call = send_email.await_args_list[0].kwargs
    interviewer_call = send_email.await_args_list[1].kwargs
    assert candidate_call["to_email"] == "asha@example.com"
    assert len(candidate_call["attachments"]) == 2
    assert candidate_call["attachments"][1] == resume_attachment
    assert interviewer_call["to_email"] == "priya@example.com"
    assert len(interviewer_call["attachments"]) == 1
    assert create_notification.await_count == 3
    assert result == {"resume_attached": True, "resume_status": "attached"}


def test_get_resume_attachment_uses_resume_from_exact_application():
    resumes_by_application = {
        "app-job-a": SimpleNamespace(
            file_name="resume-a.pdf",
            blob_ref="resumes/candidate-1/resume-a.pdf",
            file_path=None,
        ),
        "app-job-b": SimpleNamespace(
            file_name="resume-b.pdf",
            blob_ref="resumes/candidate-1/resume-b.pdf",
            file_path=None,
        ),
    }

    async def get_application_resume(session, application_id):
        return resumes_by_application[application_id]

    def fetch_object_bytes(blob_ref):
        return (f"bytes:{blob_ref}".encode(), "application/pdf")

    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_candidate_resume_for_interview",
        new=AsyncMock(side_effect=get_application_resume),
    ) as get_resume, patch(
        "app.service.employer_service.interview_service.s3_service.fetch_object_bytes",
        side_effect=fetch_object_bytes,
    ) as fetch:
        resume_a = asyncio.run(
            InterviewService._get_resume_attachment(
                session=SimpleNamespace(),
                application_id="app-job-a",
                interview_id="interview-a",
            )
        )
        resume_b = asyncio.run(
            InterviewService._get_resume_attachment(
                session=SimpleNamespace(),
                application_id="app-job-b",
                interview_id="interview-b",
            )
        )

    assert resume_a == (
        "resume-a.pdf",
        b"bytes:resumes/candidate-1/resume-a.pdf",
        "application/pdf",
    )
    assert resume_b == (
        "resume-b.pdf",
        b"bytes:resumes/candidate-1/resume-b.pdf",
        "application/pdf",
    )
    assert get_resume.await_args_list[0].kwargs["application_id"] == "app-job-a"
    assert get_resume.await_args_list[1].kwargs["application_id"] == "app-job-b"
    assert fetch.call_args_list[0].args[0] == "resumes/candidate-1/resume-a.pdf"
    assert fetch.call_args_list[1].args[0] == "resumes/candidate-1/resume-b.pdf"


def test_get_resume_attachment_missing_application_resume_does_not_fallback():
    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_candidate_resume_for_interview",
        new_callable=AsyncMock,
        return_value=None,
    ) as get_resume, patch(
        "app.service.employer_service.interview_service.s3_service.fetch_object_bytes",
    ) as fetch:
        result = asyncio.run(
            InterviewService._get_resume_attachment(
                session=SimpleNamespace(),
                application_id="app-without-resume",
                interview_id="interview-1",
            )
        )

    assert result is None
    get_resume.assert_awaited_once()
    fetch.assert_not_called()


def test_interview_notifications_report_unavailable_resume_when_file_fetch_fails():
    interview = _interview()

    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=_email_details("hr@example.com"),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewService._get_resume_attachment",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service."
        "EmailService.send_interview_scheduled_email",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "NotificationService.create_notification",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            InterviewService._send_interview_notifications(
                session=None,
                application_id="app-1",
                interview=interview,
                email_sender=AsyncMock(),
            )
        )

    assert result == {"resume_attached": False, "resume_status": "unavailable"}


def test_interview_notifications_report_not_provided_when_application_has_no_resume():
    interview = _interview()
    email_details = list(_email_details("hr@example.com"))
    email_details[-1] = None

    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=tuple(email_details),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewService._get_resume_attachment",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service."
        "NotificationService.create_notification",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            InterviewService._send_interview_notifications(
                session=None,
                application_id="app-1",
                interview=interview,
                email_sender=AsyncMock(),
            )
        )

    assert result == {"resume_attached": False, "resume_status": "not_provided"}


def test_schedule_request_accepts_interviewer_emails_without_ids():
    request = ScheduleInterviewRequest(
        interview_round="HR Discussion",
        interview_date=date.today() + timedelta(days=1),
        interview_time=time(10, 30),
        end_time=time(11, 30),
        mode=InterviewMode.ONLINE,
        meeting_link="https://meet.example.com/abc",
        interviewer_emails=["priya@example.com"],
    )

    assert request.interviewer_ids is None
    assert request.interviewer_emails == ["priya@example.com"]


def test_schedule_request_accepts_custom_round_name():
    request = ScheduleInterviewRequest(
        interview_round="Founder Round",
        interview_date=date.today() + timedelta(days=1),
        interview_time=time(10, 30),
        end_time=time(11, 30),
        mode=InterviewMode.ONLINE,
        meeting_link="https://meet.example.com/abc",
        interviewer_emails=["priya@example.com"],
    )

    assert request.interview_round == "Founder Round"


def test_schedule_request_rejects_empty_round_name():
    with pytest.raises(ValidationError):
        ScheduleInterviewRequest(
            interview_round="   ",
            interview_date=date.today() + timedelta(days=1),
            interview_time=time(10, 30),
            end_time=time(11, 30),
            mode=InterviewMode.ONLINE,
            meeting_link="https://meet.example.com/abc",
            interviewer_emails=["priya@example.com"],
        )


def test_schedule_rounds_request_accepts_exactly_20_rounds():
    request = ScheduleInterviewRoundsRequest(
        rounds=[
            ScheduleInterviewRequest(
                round_number=index,
                interview_round=f"Round {index}",
                interview_date=date.today() + timedelta(days=index),
                interview_time=time(10, 30),
                end_time=time(11, 30),
                mode=InterviewMode.ONLINE,
                meeting_link=f"https://meet.example.com/{index}",
                interviewer_emails=["priya@example.com"],
            )
            for index in range(1, 21)
        ]
    )

    assert len(request.rounds) == 20


def test_schedule_rounds_request_rejects_21st_round():
    with pytest.raises(ValidationError):
        ScheduleInterviewRoundsRequest(
            rounds=[
                ScheduleInterviewRequest(
                    round_number=min(index, 20),
                    interview_round=f"Round {index}",
                    interview_date=date.today() + timedelta(days=index),
                    interview_time=time(10, 30),
                    end_time=time(11, 30),
                    mode=InterviewMode.ONLINE,
                    meeting_link=f"https://meet.example.com/{index}",
                    interviewer_emails=["priya@example.com"],
                )
                for index in range(1, 22)
            ]
        )


def test_schedule_interview_accepts_interviewer_emails_and_returns_assigned_interviewers():
    interviewer_id = uuid4()
    interviewer = SimpleNamespace(
        user_id=interviewer_id,
        email="priya@example.com",
        first_name="Priya",
        last_name="Recruiter",
    )

    with patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_application_for_employer",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(application_status="SHORTLISTED"),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_duplicate_interview",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_active_interviewer_users_by_emails",
        new_callable=AsyncMock,
        return_value=[interviewer],
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.create_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview: interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.update_status",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.replace_interviewers",
        new_callable=AsyncMock,
    ) as replace_interviewers, patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_active_users_by_ids",
        new_callable=AsyncMock,
        return_value=[interviewer],
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.update_interview",
        new_callable=AsyncMock,
        side_effect=lambda session, interview: interview,
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewHistoryRepo.create_history",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "ShortlistedCandidatesRepo.get_interview_email_details",
        new_callable=AsyncMock,
        return_value=_email_details(),
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_interviewer_emails",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_assigned_interviewers",
        new_callable=AsyncMock,
        return_value=[
            (interviewer_id, "Priya", "Recruiter", "priya@example.com", "ROLE_RECRUITER")
        ],
    ), patch(
        "app.service.employer_service.interview_service."
        "NotificationService.create_notification",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.interview_service."
        "EmailService.send_interview_scheduled_email",
        new_callable=AsyncMock,
    ):
        result = asyncio.run(
            InterviewService.schedule_interview(
                session=SimpleNamespace(),
                employer_id="emp-1",
                application_id="app-1",
                request=_request(interviewer_emails=["priya@example.com"]),
                performed_by="user-1",
            )
        )

    replace_interviewers.assert_awaited_once()
    assert result.assigned_interviewers[0].email == "priya@example.com"
    assert result.assigned_interviewers[0].role == "ROLE_RECRUITER"


def test_schedule_interview_rejects_invalid_interviewer_emails():
    with patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.get_active_interviewer_users_by_emails",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                InterviewService._validate_interviewers(
                    session=SimpleNamespace(),
                    interviewer_ids=None,
                    interviewer_emails=["missing@example.com"],
                )
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == (
        "One or more interviewer emails are invalid, inactive, or not eligible."
    )


def test_schedule_rounds_request_accepts_interviewer_emails_per_round():
    request = ScheduleInterviewRoundsRequest(
        rounds=[
            ScheduleInterviewRequest(
                round_number=1,
                interview_round="HR Discussion",
                interview_date=date.today() + timedelta(days=1),
                interview_time=time(10, 30),
                end_time=time(11, 30),
                mode=InterviewMode.ONLINE,
                meeting_link="https://meet.example.com/abc",
                interviewer_emails=["priya@example.com"],
            ),
            ScheduleInterviewRequest(
                round_number=2,
                interview_round="Technical Round",
                interview_date=date.today() + timedelta(days=2),
                interview_time=time(12, 30),
                end_time=time(13, 30),
                mode=InterviewMode.ONLINE,
                meeting_link="https://meet.example.com/def",
                interviewer_emails=["neel@example.com"],
            ),
        ]
    )

    assert len(request.rounds) == 2


def test_interviewer_lookup_returns_active_eligible_users():
    interviewer_id = uuid4()

    with patch(
        "app.service.employer_service.interview_service."
        "InterviewInterviewerRepo.list_active_interviewers",
        new_callable=AsyncMock,
        return_value=(
            1,
            [
                (
                    interviewer_id,
                    "Priya",
                    "Recruiter",
                    "priya@example.com",
                    "ROLE_RECRUITER",
                    "ACTIVE",
                )
            ],
        ),
    ):
        result = asyncio.run(
            InterviewService.list_interviewers(
                session=SimpleNamespace(),
                search="priya",
                page=1,
                page_size=20,
            )
        )

    assert result.total == 1
    assert result.items[0].user_id == str(interviewer_id)
    assert result.items[0].role == "ROLE_RECRUITER"
    assert result.items[0].status == "ACTIVE"


def test_get_interview_returns_completed_round_history_and_next_round_number():
    round_one = _interview(
        round_number=1,
        interview_round="Technical Round",
        status="COMPLETED",
    )
    completed_at = date.today()
    setattr(round_one, "completed_at", completed_at)

    round_two = _interview(
        round_number=2,
        interview_round="Manager Round",
        interview_time=time(12, 30),
        status="SCHEDULED",
    )

    with patch(
        "app.service.employer_service.interview_service."
        "InterviewRepo.get_by_application_for_employer",
        new_callable=AsyncMock,
        return_value=[round_one, round_two],
    ), patch(
        "app.service.employer_service.interview_service."
        "InterviewService._assigned_interviewers",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = asyncio.run(
            InterviewService.get_interview(
                session=None,
                employer_id="emp-1",
                application_id="app-1",
            )
        )

    assert result.next_round_number == 3
    assert [interview.status for interview in result.interviews] == [
        "COMPLETED",
        "SCHEDULED",
    ]
    assert result.interviews[0].round_number == 1
    assert result.interviews[0].start_time == result.interviews[0].interview_time
    assert result.interviews[0].completed_at == completed_at.isoformat()


def test_duplicate_round_number_query_checks_all_statuses():
    captured = {}

    class Result:
        def scalar_one_or_none(self):
            return None

    class Session:
        async def execute(self, statement):
            captured["sql"] = str(
                statement.compile(compile_kwargs={"literal_binds": True})
            )
            return Result()

    asyncio.run(
        InterviewRepo.get_duplicate_interview(
            session=Session(),
            application_id="app-1",
            interview_date=date.today() + timedelta(days=1),
            interview_time=time(10, 30),
            round_number=1,
        )
    )

    assert "interviews.round_number = 1" in captured["sql"]
    assert "interviews.status IN" not in captured["sql"]
