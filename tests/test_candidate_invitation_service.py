import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.utils.utc import utc_now_naive
from fastapi import HTTPException

from app.service.employer_service.invitations_service import (
    CandidateInvitationsService,
    EmployerInvitationsService,
)


def test_accept_invitation_returns_job_navigation_data():
    invitation = SimpleNamespace(
        invitation_id="inv-1",
        candidate_id="cand-1",
        job_id="job-1",
        status="PENDING",
        invited_at=None,
        viewed_at=None,
        responded_at=None,
        accepted_at=None,
        rejected_at=None,
        created_at=utc_now_naive(),
        updated_at=utc_now_naive(),
    )
    accepted = SimpleNamespace(**{**invitation.__dict__, "status": "ACCEPTED"})

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService._get_candidate_id_from_payload",
        new_callable=AsyncMock,
        return_value="cand-1",
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_invitation_by_id_and_candidate",
        new_callable=AsyncMock,
        return_value=invitation,
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.update_invitation_status",
        new_callable=AsyncMock,
        return_value=accepted,
    ) as update_status:
        result = asyncio.run(
            CandidateInvitationsService.accept_invitation(
                session=None,
                payload={"user_id": "22222222-2222-2222-2222-222222222222"},
                invitation_id="inv-1",
            )
        )

    assert result.status == "ACCEPTED"
    assert result.job_id == "job-1"
    assert result.job_details_url == "/candidate/jobs/job-1"
    update_status.assert_awaited_once()
    assert update_status.await_args.kwargs["new_status"] == "ACCEPTED"
    assert update_status.await_args.kwargs["accepted_at"] is not None


def test_employer_active_jobs_expires_deadlines_with_keyword_session():
    class FakeSession:
        async def execute(self, *args, **kwargs):
            pass

    job = SimpleNamespace(
        job_id="job-1",
        title="Backend Developer",
        team="Engineering",
        location="Hyderabad",
        employment_type="FULL_TIME",
        no_of_openings=2,
        created_at=datetime(2026, 8, 5, 9, 30),
    )

    with patch(
        "app.service.employer_service.invitations_service.EmployerInvitationsService._get_employer_id_from_payload",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.invitations_service.JobRepository.expire_jobs_past_deadline",
        new_callable=AsyncMock,
        return_value=0,
    ) as expire_jobs, patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.list_active_jobs_for_invitation",
        new_callable=AsyncMock,
        return_value=(1, [(job, 3)]),
    ):
        result = asyncio.run(
            EmployerInvitationsService.list_active_jobs(
                session=FakeSession(),
                payload={"user_id": "11111111-1111-1111-1111-111111111111"},
                page=1,
                page_size=100,
            )
        )

    expire_jobs.assert_awaited_once()
    assert expire_jobs.await_args.args == ()
    assert expire_jobs.await_args.kwargs["employer_id"] == "emp-1"
    assert result.total_records == 1
    assert result.items[0].application_count == 3


def test_accept_invitation_allows_viewed_status():
    invitation = SimpleNamespace(
        invitation_id="inv-1",
        candidate_id="cand-1",
        job_id="job-1",
        status="VIEWED",
        invited_at=None,
        viewed_at=utc_now_naive(),
        responded_at=None,
        accepted_at=None,
        rejected_at=None,
        created_at=utc_now_naive(),
        updated_at=utc_now_naive(),
    )
    accepted = SimpleNamespace(**{**invitation.__dict__, "status": "ACCEPTED"})

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService._get_candidate_id_from_payload",
        new_callable=AsyncMock,
        return_value="cand-1",
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_invitation_by_id_and_candidate",
        new_callable=AsyncMock,
        return_value=invitation,
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.update_invitation_status",
        new_callable=AsyncMock,
        return_value=accepted,
    ) as update_status:
        result = asyncio.run(
            CandidateInvitationsService.accept_invitation(
                session=None,
                payload={"user_id": "22222222-2222-2222-2222-222222222222"},
                invitation_id="inv-1",
            )
        )

    assert result.status == "ACCEPTED"
    update_status.assert_awaited_once()


def test_accept_invitation_notifies_employer():
    class FakeSession:
        async def execute(self, *args, **kwargs):
            pass

    invitation = SimpleNamespace(
        invitation_id="inv-1",
        candidate_id="cand-1",
        job_id="job-1",
        status="PENDING",
        invited_at=None,
        viewed_at=None,
        responded_at=None,
        accepted_at=None,
        rejected_at=None,
        created_at=utc_now_naive(),
        updated_at=utc_now_naive(),
    )
    accepted = SimpleNamespace(**{**invitation.__dict__, "status": "ACCEPTED"})
    context = (
        accepted,
        SimpleNamespace(job_id="job-1", title="Backend Developer"),
        SimpleNamespace(user_id="employer-user-1"),
        SimpleNamespace(first_name="Alice", middle_name=None, last_name="Example"),
    )

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService._get_candidate_id_from_payload",
        new_callable=AsyncMock,
        return_value="cand-1",
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_invitation_by_id_and_candidate",
        new_callable=AsyncMock,
        return_value=invitation,
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.update_invitation_status",
        new_callable=AsyncMock,
        return_value=accepted,
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_invitation_notification_context",
        new_callable=AsyncMock,
        return_value=context,
    ), patch(
        "app.service.employer_service.invitations_service.SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.invitations_service.NotificationService.create_notification",
        new_callable=AsyncMock,
    ) as create_notification:
        result = asyncio.run(
            CandidateInvitationsService.accept_invitation(
                session=FakeSession(),
                payload={"user_id": "22222222-2222-2222-2222-222222222222"},
                invitation_id="inv-1",
            )
        )

    assert result.status == "ACCEPTED"
    create_notification.assert_awaited_once()
    assert create_notification.await_args.kwargs["recipient_id"] == "employer-user-1"
    assert create_notification.await_args.kwargs["notification_type"] == "INVITATION_ACCEPTED"
    assert create_notification.await_args.kwargs["reference_id"] == "inv-1"


def test_reject_invitation_returns_400_when_already_accepted():
    invitation = SimpleNamespace(
        invitation_id="inv-1",
        candidate_id="cand-1",
        job_id="job-1",
        status="ACCEPTED",
    )

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService._get_candidate_id_from_payload",
        new_callable=AsyncMock,
        return_value="cand-1",
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_invitation_by_id_and_candidate",
        new_callable=AsyncMock,
        return_value=invitation,
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.update_invitation_status",
        new_callable=AsyncMock,
    ) as update_status:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                CandidateInvitationsService.reject_invitation(
                    session=None,
                    payload={"user_id": "22222222-2222-2222-2222-222222222222"},
                    invitation_id="inv-1",
                )
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invitation is not pending"
    update_status.assert_not_called()


def test_accept_invitation_returns_404_for_missing_or_unowned_invitation():
    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService._get_candidate_id_from_payload",
        new_callable=AsyncMock,
        return_value="cand-1",
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_invitation_by_id_and_candidate",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.update_invitation_status",
        new_callable=AsyncMock,
    ) as update_status:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                CandidateInvitationsService.accept_invitation(
                    session=None,
                    payload={"user_id": "22222222-2222-2222-2222-222222222222"},
                    invitation_id="missing",
                )
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Invitation not found"
    update_status.assert_not_called()


def _candidate_invitation_details_row(invitation_status: str, viewed_at=None):
    invitation = SimpleNamespace(
        invitation_id="inv-1",
        candidate_id="cand-1",
        job_id="job-1",
        status=invitation_status,
        custom_message="Please take a look",
        invited_at=None,
        viewed_at=viewed_at,
        responded_at=None,
        accepted_at=None,
        rejected_at=None,
        created_at=utc_now_naive(),
    )
    job = SimpleNamespace(
        job_id="job-1",
        title="Backend Developer",
        location="Hyderabad",
        employment_type="FULL_TIME",
        work_mode="REMOTE",
        experience_min=2,
        experience_max=5,
        salary_min=None,
        salary_max=None,
        salary_currency="INR",
        salary_period="YEARLY",
        description="Build APIs",
        created_at=utc_now_naive(),
        application_deadline=None,
    )
    employer = SimpleNamespace(
        id="emp-1",
        company_name="NMK",
        company_logo_url=None,
        company_email="hr@nmk.com",
        company_website=None,
        website_url=None,
        company_location="Hyderabad",
        location=None,
        job_title="Recruiter",
        department="Talent",
    )
    recruiter = SimpleNamespace(
        user_id="user-1",
        first_name="Riya",
        middle_name=None,
        last_name="Recruiter",
        email="riya@nmk.com",
        profile_image_url=None,
    )
    company = SimpleNamespace(
        company_name="NMK Global",
        logo_url=None,
        logo_path=None,
        contact_email=None,
        website=None,
        location=None,
    )
    return invitation, job, employer, recruiter, company, ["Python", "FastAPI"]


def test_get_invitation_details_marks_pending_as_viewed():
    row = _candidate_invitation_details_row("PENDING")
    viewed_at = utc_now_naive()
    viewed = SimpleNamespace(**{**row[0].__dict__, "status": "VIEWED", "viewed_at": viewed_at})

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService._get_candidate_id_from_payload",
        new_callable=AsyncMock,
        return_value="cand-1",
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_candidate_invitation_details",
        new_callable=AsyncMock,
        return_value=row,
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.mark_viewed",
        new_callable=AsyncMock,
        return_value=viewed,
    ) as mark_viewed:
        result = asyncio.run(
            CandidateInvitationsService.get_invitation_details(
                session=None,
                payload={"user_id": "22222222-2222-2222-2222-222222222222"},
                invitation_id="inv-1",
            )
        )

    assert result.status == "VIEWED"
    assert result.viewed_at == viewed_at
    mark_viewed.assert_awaited_once()


@pytest.mark.parametrize("status", ["VIEWED", "ACCEPTED", "REJECTED", "EXPIRED", "WITHDRAWN"])
def test_get_invitation_details_does_not_overwrite_non_pending_status(status):
    viewed_at = utc_now_naive()
    row = _candidate_invitation_details_row(status, viewed_at=viewed_at)

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService._get_candidate_id_from_payload",
        new_callable=AsyncMock,
        return_value="cand-1",
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_candidate_invitation_details",
        new_callable=AsyncMock,
        return_value=row,
    ), patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.mark_viewed",
        new_callable=AsyncMock,
    ) as mark_viewed:
        result = asyncio.run(
            CandidateInvitationsService.get_invitation_details(
                session=None,
                payload={"user_id": "22222222-2222-2222-2222-222222222222"},
                invitation_id="inv-1",
            )
        )

    assert result.status == status
    assert result.viewed_at == viewed_at
    mark_viewed.assert_not_called()
