from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncio
import pytest
from app.utils.utc import utc_now_naive
from fastapi import HTTPException

from app.job_application_schema import JobApplicationCreateSchema
from app.service.candidate_service import CandidateProfileService
from app.service.job_application_service import JobApplicationService
from app.service.subscription.subscription_validator import SubscriptionValidator


def _active_subscription(user_id, subscription_id):
    now = utc_now_naive()
    return SimpleNamespace(
        user_subscription_id=uuid4(),
        user_id=user_id,
        subscription_id=subscription_id,
        role="EMPLOYER",
        start_date=now,
        end_date=now + timedelta(days=30),
        status="ACTIVE",
    )


def _plan(subscription_id, feature_flags):
    return SimpleNamespace(
        subscription_id=subscription_id,
        subscription_type="EMPLOYER",
        is_active=True,
        max_published_jobs=None,
        max_job_alerts=None,
        max_resume_uploads=None,
        is_featured=False,
        feature_flags=feature_flags,
        price=Decimal("0.00"),
        currency="INR",
        duration_days=30,
    )


def test_subscription_validator_accepts_camelcase_feature_flags():
    user_id = uuid4()
    subscription_id = uuid4()
    active = _active_subscription(user_id, subscription_id)
    plan = _plan(
        subscription_id,
        {
            "candidateSearch": True,
            "candidateInvitations": True,
            "candidateInvitationsPerWeek": 7,
        },
    )

    with (
        patch(
            "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_active_subscription",
            new_callable=AsyncMock,
            return_value=active,
        ),
        patch(
            "app.service.subscription.subscription_validator.SubscriptionRepository.get_by_id",
            new_callable=AsyncMock,
            return_value=plan,
        ),
    ):
        validator = SubscriptionValidator(
            session=AsyncMock(),
            user_id=user_id,
            role="EMPLOYER",
        )
        assert asyncio.run(validator.has_feature("candidate_search")) is True
        assert asyncio.run(validator.has_feature("candidate_invitations")) is True
        assert asyncio.run(validator.get_limit("candidate_invitations")) is None
        assert asyncio.run(validator.get_limit("candidate_invitations_per_week")) == 7


@pytest.mark.asyncio
async def test_duplicate_resume_subscription_limit_can_raise_above_floor():
    """A subscription plan is allowed to grant *more* than the platform
    floor of MAX_RESUME_COUNT (5) resumes -- e.g. a premium tier offering
    10 -- and that higher ceiling should be enforced instead of the floor."""
    user_id = uuid4()
    profile = SimpleNamespace(candidate_id="candidate-1")
    ten_resumes = [SimpleNamespace(resume_id=f"resume-{i}") for i in range(10)]

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_resumes",
            new_callable=AsyncMock,
            return_value=ten_resumes,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.get_limit",
            new_callable=AsyncMock,
            return_value=10,
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await CandidateProfileService.duplicate_resume(
                session=AsyncMock(),
                user_id=user_id,
                resume_id="resume-1",
            )

    assert exc.value.status_code == 403
    assert "up to 10 resumes" in exc.value.detail


@pytest.mark.asyncio
async def test_duplicate_resume_subscription_limit_cannot_drop_below_floor():
    """A subscription plan's configured resume limit can never push a
    candidate below the platform floor of MAX_RESUME_COUNT (5) -- e.g. a
    stale/misconfigured plan value of 1 must not cap someone with fewer
    than 5 resumes."""
    user_id = uuid4()
    profile = SimpleNamespace(candidate_id="candidate-1")
    five_resumes = [SimpleNamespace(resume_id=f"resume-{i}") for i in range(5)]

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_resumes",
            new_callable=AsyncMock,
            return_value=five_resumes,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.get_limit",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await CandidateProfileService.duplicate_resume(
                session=AsyncMock(),
                user_id=user_id,
                resume_id="resume-1",
            )

    assert exc.value.status_code == 403
    assert "up to 5 resumes" in exc.value.detail


@pytest.mark.asyncio
async def test_create_job_alert_enforces_configured_limit():
    from app.candidate_schema import JobAlertUpsertSchema

    user_id = uuid4()
    profile = SimpleNamespace(candidate_id="candidate-1")
    payload = JobAlertUpsertSchema(
        title="Backend alerts",
        job_category="Engineering",
        job_title="Backend Engineer",
        preferred_location="Hyderabad",
        experience_level="MID_LEVEL",
        employment_type="FULL_TIME",
        notification_preference="EMAIL",
    )

    with (
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_profile_by_user_id",
            new_callable=AsyncMock,
            return_value=profile,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.candidate_service.SubscriptionValidator.get_limit",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch(
            "app.service.candidate_service.CandidateProfileRepo.get_job_alerts",
            new_callable=AsyncMock,
            return_value=[SimpleNamespace(alert_id="alert-1")],
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await CandidateProfileService.create_job_alert(
                session=AsyncMock(),
                user_id=user_id,
                data=payload,
            )

    assert exc.value.status_code == 403
    assert "up to 1 job alerts" in exc.value.detail


@pytest.mark.asyncio
async def test_update_and_delete_job_alert_require_subscription_feature():
    from app.candidate_schema import JobAlertUpdateSchema

    user_id = uuid4()
    denied = HTTPException(
        status_code=403,
        detail="Subscription does not include job_alerts.",
    )

    with patch(
        "app.service.candidate_service.SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
        side_effect=denied,
    ) as require_feature:
        with pytest.raises(HTTPException) as update_exc:
            await CandidateProfileService.update_job_alert(
                session=AsyncMock(),
                user_id=user_id,
                alert_id="alert-1",
                data=JobAlertUpdateSchema(title="Blocked"),
            )
        with pytest.raises(HTTPException) as delete_exc:
            await CandidateProfileService.delete_job_alert(
                session=AsyncMock(),
                user_id=user_id,
                alert_id="alert-1",
            )

    assert update_exc.value.status_code == 403
    assert delete_exc.value.status_code == 403
    assert require_feature.await_count == 2


@pytest.mark.asyncio
async def test_accept_recruiter_invitation_requires_candidate_connection_feature():
    from app.service.employer_service.invitations_service import (
        CandidateInvitationsService,
    )

    user_id = uuid4()
    with patch(
        "app.service.employer_service.invitations_service.SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=403, detail="blocked"),
    ) as require_feature, patch(
        "app.service.employer_service.invitations_service.InvitationsRepository.get_invitation_by_id_and_candidate",
        new_callable=AsyncMock,
    ) as get_invitation:
        with pytest.raises(HTTPException) as exc:
            await CandidateInvitationsService.accept_invitation(
                session=AsyncMock(),
                payload={"user_id": str(user_id)},
                invitation_id="inv-1",
            )

    assert exc.value.status_code == 403
    require_feature.assert_awaited_once_with("recruiters_can_contact_candidate")
    get_invitation.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_candidate_invitation_uses_weekly_limit():
    from app.service.employer_service.invitations_service import (
        EmployerInvitationsService,
    )
    from app.schema.invitations import SendInvitationRequest

    employer_user_id = uuid4()
    employer = SimpleNamespace(id="employer-1")
    candidate_result = SimpleNamespace(
        scalar_one_or_none=lambda: SimpleNamespace(candidate_id="candidate-1")
    )
    job = SimpleNamespace(job_id="job-1", status="PUBLISHED")
    created = SimpleNamespace(invitation_id="inv-1")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=candidate_result)

    with (
        patch(
            "app.service.employer_service.invitations_service.EmployerProfileRepository.get_by_user_id",
            new_callable=AsyncMock,
            return_value=employer,
        ),
        patch(
            "app.service.employer_service.invitations_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ) as require_feature,
        patch(
            "app.service.employer_service.invitations_service.SubscriptionValidator.ensure_limit_available",
            new_callable=AsyncMock,
        ) as ensure_limit_available,
        patch(
            "app.service.employer_service.invitations_service.SubscriptionValidator.consume_limit",
            new_callable=AsyncMock,
        ) as consume_limit,
        patch(
            "app.service.employer_service.invitations_service.InvitationsRepository.get_job_owned_by_employer",
            new_callable=AsyncMock,
            return_value=job,
        ),
        patch(
            "app.service.employer_service.invitations_service.InvitationsRepository.has_duplicate_active_invitation",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.service.employer_service.invitations_service.InvitationsRepository.create_invitation",
            new_callable=AsyncMock,
            return_value=created,
        ),
    ):
        result = await EmployerInvitationsService.send_invitation(
            session=session,
            payload={"user_id": str(employer_user_id)},
            candidate_id="candidate-1",
            request=SendInvitationRequest(job_id="job-1", message="Please apply"),
            message="Please apply",
        )

    assert result is created
    require_feature.assert_awaited_once_with("candidate_invitations")
    ensure_limit_available.assert_awaited_once_with(
        "candidate_invitations_per_week",
        period="week",
    )
    consume_limit.assert_awaited_once_with(
        "candidate_invitations_per_week",
        period="week",
    )


@pytest.mark.asyncio
async def test_send_candidate_invitation_weekly_limit_blocks_before_creation():
    from app.service.employer_service.invitations_service import (
        EmployerInvitationsService,
    )
    from app.schema.invitations import SendInvitationRequest

    employer_user_id = uuid4()
    employer = SimpleNamespace(id="employer-1")
    denied = HTTPException(status_code=403, detail="weekly limit reached")

    with (
        patch(
            "app.service.employer_service.invitations_service.EmployerProfileRepository.get_by_user_id",
            new_callable=AsyncMock,
            return_value=employer,
        ),
        patch(
            "app.service.employer_service.invitations_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.employer_service.invitations_service.SubscriptionValidator.ensure_limit_available",
            new_callable=AsyncMock,
            side_effect=denied,
        ) as ensure_limit_available,
        patch(
            "app.service.employer_service.invitations_service.InvitationsRepository.create_invitation",
            new_callable=AsyncMock,
        ) as create_invitation,
    ):
        with pytest.raises(HTTPException) as exc:
            await EmployerInvitationsService.send_invitation(
                session=AsyncMock(),
                payload={"user_id": str(employer_user_id)},
                candidate_id="candidate-1",
                request=SendInvitationRequest(job_id="job-1", message="Please apply"),
                message="Please apply",
            )

    assert exc.value.status_code == 403
    ensure_limit_available.assert_awaited_once_with(
        "candidate_invitations_per_week",
        period="week",
    )
    create_invitation.assert_not_awaited()


@pytest.mark.asyncio
async def test_weekly_limit_uses_current_week_usage_window():
    user_id = uuid4()
    subscription_id = uuid4()
    active = _active_subscription(user_id, subscription_id)
    plan = _plan(
        subscription_id,
        {
            "candidate_invitations": True,
            "candidate_invitations_per_week": 2,
        },
    )

    with (
        patch(
            "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_active_subscription",
            new_callable=AsyncMock,
            return_value=active,
        ),
        patch(
            "app.service.subscription.subscription_validator.SubscriptionRepository.get_by_id",
            new_callable=AsyncMock,
            return_value=plan,
        ),
        patch(
            "app.service.subscription.subscription_validator.UserSubscriptionRepository.get_usage",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(used_count=2),
        ) as get_usage,
    ):
        validator = SubscriptionValidator(
            session=AsyncMock(),
            user_id=user_id,
            role="EMPLOYER",
        )
        with pytest.raises(HTTPException) as exc:
            await validator.ensure_limit_available(
                "candidate_invitations_per_week",
                period="week",
            )

    assert exc.value.status_code == 403
    _, kwargs = get_usage.await_args
    assert kwargs["feature_name"] == "candidate_invitations_per_week"
    assert kwargs["period_start"].weekday() == 0
    assert (kwargs["period_end"] - kwargs["period_start"]).days == 7


@pytest.mark.asyncio
async def test_job_posting_create_checks_published_job_limit():
    from app.schema.job import PostJobRequestSchema
    from app.service.employer_service.job_service import JobService

    request = PostJobRequestSchema(
        job_title="Backend Engineer",
        job_description="Build APIs",
        employment_type="FULL_TIME",
        experience_required="3-5",
        location="Hyderabad",
        work_mode="REMOTE",
        skills=["Python"],
        number_of_openings=1,
        company_name="NMK",
        contact_email="hr@example.com",
    )

    with patch.object(
        JobService,
        "_require_employer",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.SubscriptionValidator.get_limit",
        new_callable=AsyncMock,
        side_effect=[3],
    ) as get_limit, patch(
        "app.service.employer_service.job_service.JobRepository.count_published_jobs",
        new_callable=AsyncMock,
        return_value=1,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.find_duplicate_active_job",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.create_job",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(job_id="job-1", title="Backend Engineer", status="PUBLISHED"),
    ) as create_job, patch(
        "app.service.employer_service.job_service.JobAlertNotificationService.notify_matching_candidates",
        new_callable=AsyncMock,
    ) as notify_alerts, patch(
        "app.service.employer_service.job_service.ActivityLogService.create_log_for_user_id",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.NotificationService.create_for_super_admins",
        new_callable=AsyncMock,
    ):
        await JobService.create_post_job(
            session=AsyncMock(),
            payload={"user_id": str(uuid4())},
            employer_id="employer-1",
            request=request,
            idempotency_key=None,
        )

    create_job.assert_awaited_once()
    get_limit.assert_awaited_once_with("max_published_jobs")
    notify_alerts.assert_awaited_once()


@pytest.mark.asyncio
async def test_job_posting_create_blocks_when_published_job_limit_reached():
    from app.schema.job import PostJobRequestSchema
    from app.service.employer_service.job_service import JobService

    request = PostJobRequestSchema(
        job_title="Backend Engineer",
        job_description="Build APIs",
        employment_type="FULL_TIME",
        experience_required="3-5",
        location="Hyderabad",
        work_mode="REMOTE",
        skills=["Python"],
        number_of_openings=1,
        company_name="NMK",
        contact_email="hr@example.com",
    )

    with patch.object(
        JobService,
        "_require_employer",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.SubscriptionValidator.get_limit",
        new_callable=AsyncMock,
        return_value=1,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.count_published_jobs",
        new_callable=AsyncMock,
        return_value=1,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.create_job",
        new_callable=AsyncMock,
    ) as create_job:
        with pytest.raises(HTTPException) as exc:
            await JobService.create_post_job(
                session=AsyncMock(),
                payload={"user_id": str(uuid4())},
                employer_id="employer-1",
                request=request,
                idempotency_key=None,
            )

    assert exc.value.status_code == 403
    assert "publish up to 1 jobs" in exc.value.detail
    create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_job_posting_create_draft_does_not_send_job_alerts():
    from app.schema.job import PostJobRequestSchema
    from app.service.employer_service.job_service import JobService

    request = PostJobRequestSchema(
        job_title="Backend Engineer",
        job_description="Build APIs",
        employment_type="FULL_TIME",
        experience_required="3-5",
        location="Hyderabad",
        work_mode="REMOTE",
        skills=["Python"],
        number_of_openings=1,
        company_name="NMK",
        contact_email="hr@example.com",
        status="DRAFT",
    )

    with patch.object(
        JobService,
        "_require_employer",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.SubscriptionValidator.get_limit",
        new_callable=AsyncMock,
        return_value=3,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.find_duplicate_active_job",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.employer_service.job_service.JobRepository.create_job",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(job_id="job-1", title="Backend Engineer", status="DRAFT"),
    ), patch(
        "app.service.employer_service.job_service.JobAlertNotificationService.notify_matching_candidates",
        new_callable=AsyncMock,
    ) as notify_alerts, patch(
        "app.service.employer_service.job_service.ActivityLogService.create_log_for_user_id",
        new_callable=AsyncMock,
    ), patch(
        "app.service.employer_service.job_service.NotificationService.create_for_super_admins",
        new_callable=AsyncMock,
    ):
        await JobService.create_post_job(
            session=AsyncMock(),
            payload={"user_id": str(uuid4())},
            employer_id="employer-1",
            request=request,
            idempotency_key=None,
        )

    notify_alerts.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_profile_create_is_not_subscription_gated():
    from app.schema.profile import CompanyProfileCreate
    from app.service.profile_service import CompanyProfileService

    with patch(
        "app.service.profile_service.EmployerProfileRepository.get_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc:
            await CompanyProfileService.create(
                session=AsyncMock(),
                payload={"user_id": str(uuid4())},
                request=CompanyProfileCreate(
                    company_name="NMK",
                    website="https://nmk.example.com",
                    industry="Technology",
                    company_size="1-10",
                    founded_year=2020,
                    description="NMK builds hiring software for modern teams.",
                    headquarters_country="India",
                    headquarters_city="Hyderabad",
                    contact_email="hr@nmk.example.com",
                    contact_phone="+919999999999",
                ),
            )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Employer profile not found"


@pytest.mark.asyncio
async def test_interview_schedule_no_longer_requires_subscription_feature():
    from app.schema.interview import InterviewMode, ScheduleInterviewRequest
    from app.service.employer_service.interview_service import InterviewService

    request = ScheduleInterviewRequest(
        interview_round="HR",
        round_number=1,
        interview_date=utc_now_naive().date(),
        interview_time=utc_now_naive().time(),
        end_time=(utc_now_naive() + timedelta(hours=1)).time(),
        mode=InterviewMode.ONLINE,
        meeting_link="https://meet.example.com/abc",
        interviewer_emails=["hr@example.com"],
    )

    with patch(
        "app.service.employer_service.interview_service.ShortlistedCandidatesRepo.get_application_for_employer",
        new_callable=AsyncMock,
        return_value=None,
    ) as get_application:
        with pytest.raises(HTTPException) as exc:
            await InterviewService.schedule_interview(
                session=AsyncMock(),
                employer_id="employer-1",
                application_id="app-1",
                request=request,
                performed_by=str(uuid4()),
            )

    assert exc.value.status_code == 403
    get_application.assert_awaited_once()


@pytest.mark.asyncio
async def test_job_alert_background_delivery_skips_disabled_subscription():
    from app.service.job_alert_notification_service import JobAlertNotificationService

    alert = SimpleNamespace(
        user_id=uuid4(),
        candidate_id="candidate-1",
        alert_id="alert-1",
        job_title="Backend",
        preferred_location=None,
        experience_level=None,
        employment_type=None,
        job_category=None,
        frequency="INSTANT",
    )
    job = SimpleNamespace(job_id="job-1", title="Backend Engineer")

    with patch(
        "app.service.job_alert_notification_service.CandidateProfileRepo.get_active_job_alert_candidates",
        new_callable=AsyncMock,
        return_value=[alert],
    ), patch(
        "app.service.job_alert_notification_service.SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=403, detail="blocked"),
    ) as require_feature, patch.object(
        JobAlertNotificationService,
        "_dispatch_notification",
        new_callable=AsyncMock,
    ) as dispatch:
        await JobAlertNotificationService.notify_matching_candidates(
            session=AsyncMock(),
            job=job,
        )

    require_feature.assert_awaited_once_with("job_alerts")
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_with_existing_resume_snapshots_resume_metadata():
    user_id = uuid4()
    resume = SimpleNamespace(
        resume_id="resume-1",
        file_name="snapshot.pdf",
        blob_ref="resumes/candidate-1/snapshot.pdf",
        file_path=None,
        file_size=123,
    )
    captured = {}

    async def create_application(session, application, *, commit=True):
        captured["application"] = application
        application.application_id = "application-1"
        return application

    with (
        patch(
            "app.service.job_application_service.JobApplicationRepo._get_candidate_id",
            new_callable=AsyncMock,
            return_value="candidate-1",
        ),
        patch(
            "app.service.job_application_service.JobRepository.expire_jobs_past_deadline",
            new_callable=AsyncMock,
        ),
        patch(
            "app.service.job_application_service.JobApplicationRepo.get_job_for_application",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                job_id="job-1",
                title="Backend Engineer",
                status="ACTIVE",
                closed_at=None,
                application_deadline=None,
            ),
        ),
        patch(
            "app.service.job_application_service.JobApplicationRepo.get_resume_for_candidate",
            new_callable=AsyncMock,
            return_value=resume,
        ),
        patch(
            "app.service.job_application_service.JobApplicationRepo.application_exists",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.service.job_application_service.JobApplicationRepo.get_applications_for_candidate",
            new_callable=AsyncMock,
            return_value=(0, []),
        ),
        patch(
            "app.service.job_application_service.JobApplicationRepo.create_application",
            new=AsyncMock(side_effect=create_application),
        ),
        patch(
            "app.service.job_application_service.ActivityLogService.create_log_for_user_id",
            new_callable=AsyncMock,
        ),
    ):
        result = await JobApplicationService.apply_for_job(
            session=AsyncMock(),
            user_id=user_id,
            data=JobApplicationCreateSchema(job_id="job-1", resume_id="resume-1"),
        )

    application = captured["application"]
    assert result["application_id"] == "application-1"
    assert application.resume_file_name_snapshot == "snapshot.pdf"
    assert application.resume_blob_ref_snapshot == "resumes/candidate-1/snapshot.pdf"
    assert application.resume_file_size_snapshot == 123


@pytest.mark.asyncio
async def test_candidate_details_view_requires_search_feature_without_consuming_search_quota():
    from app.service.candidate_details_service import CandidateDetailsService

    profile = SimpleNamespace(
        candidate_id="candidate-1",
        resumes=[],
        resume_details=[],
        applications=[],
        current_location="Hyderabad",
        headline="Backend Engineer",
        summary="Builds APIs",
        total_experience=5,
    )
    user = SimpleNamespace(
        first_name="Alice",
        last_name="Example",
        email="alice@example.com",
        mobile_number="+919999999999",
    )

    with (
        patch(
            "app.service.candidate_details_service.CandidateDetailsRepo.get_candidate_details",
            new_callable=AsyncMock,
            return_value=(profile, user),
        ),
        patch(
            "app.service.candidate_details_service.SubscriptionValidator.require_feature",
            new_callable=AsyncMock,
        ) as require_feature,
        patch(
            "app.service.candidate_details_service.SubscriptionValidator.consume_limit",
            new_callable=AsyncMock,
        ) as consume_limit,
    ):
        result = await CandidateDetailsService.get_candidate_details(
            session=AsyncMock(),
            candidate_id="candidate-1",
            user_id=uuid4(),
        )

    assert result["candidate_id"] == "candidate-1"
    require_feature.assert_awaited_once_with("candidate_search")
    consume_limit.assert_not_awaited()