from __future__ import annotations

import asyncio
from datetime import date, datetime, time, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.utils.utc import utc_now_naive
from fastapi import HTTPException

from app.controller.employer_controller.dashboard import get_employer_analytics, get_employer_dashboard
from app.employer_dashboard_schema import EmployerAnalyticsFilters, EmployerDashboardFilters
from app.repository.employer_repository.dashboard_repo import EmployerDashboardRepo
from app.service.employer_service.dashboard_service import EmployerDashboardService


USER_ID = uuid4()


class DumpableResult:
    def __init__(self, **data):
        self.data = data

    def model_dump(self):
        return self.data


class FakeSession:
    pass


class FakeScalarResult:
    def all(self):
        return []


class FakeQueryResult:
    def all(self):
        return []

    def scalars(self):
        return FakeScalarResult()


class CapturingSession:
    def __init__(self):
        self.sql = None

    async def execute(self, statement):
        self.sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        return FakeQueryResult()


def test_employer_dashboard_controller_success():
    async def run_test():
        payload = {
            "user_id": str(USER_ID),
            "email": "employer@example.com",
            "roles": [{"role_code": "ROLE_EMPLOYER"}],
        }
        with patch(
            "app.controller.employer_controller.dashboard.EmployerDashboardService.get_dashboard",
            new_callable=AsyncMock,
            return_value=DumpableResult(stat_cards=[{"key": "applications", "value": 3}]),
        ) as service:
            response = await get_employer_dashboard(
                job_id="job-1",
                application_status="APPLIED",
                date_from=date(2026, 6, 1),
                date_to=date(2026, 6, 19),
                limit=10,
                payload=payload,
                session=FakeSession(),
            )

        assert response.message == "Employer dashboard fetched successfully"
        assert response.data == {"stat_cards": [{"key": "applications", "value": 3}]}
        _, kwargs = service.call_args
        filters = kwargs["filters"]
        assert filters.job_id == "job-1"
        assert filters.application_status == "APPLIED"
        assert filters.date_from == date(2026, 6, 1)
        assert filters.date_to == date(2026, 6, 19)
        assert filters.limit == 10

    asyncio.run(run_test())


def test_fetch_upcoming_interviews_orders_by_existing_model_fields():
    async def run_test():
        session = CapturingSession()

        await EmployerDashboardRepo.fetch_upcoming_interviews(
            session=session,
            employer_id="emp-1",
            limit=8,
        )

        assert "interviews.interview_date ASC" in session.sql
        assert "interviews.interview_time ASC" in session.sql
        assert "scheduled_at" not in session.sql

    asyncio.run(run_test())


def test_build_interview_row_uses_interview_date_time_and_location_fields():
    interview = SimpleNamespace(
        interview_id="int-1",
        interview_date=date(2026, 8, 6),
        interview_time=time(14, 30),
        meeting_link="https://meet.example.com/1",
        interview_location=None,
        mode="VIDEO",
        interviewer_name="Ravi",
        status="SCHEDULED",
    )
    application = SimpleNamespace(application_id="app-1")
    job = SimpleNamespace(
        job_id="job-1",
        title="Python Developer",
        status="PUBLISHED",
        location="Hyderabad",
        employment_type="FULL_TIME",
        work_mode="REMOTE",
        created_at=datetime(2026, 8, 1, 9, 0),
        application_deadline=None,
    )
    candidate = SimpleNamespace(
        candidate_id="cand-1",
        user_id=uuid4(),
        headline=None,
        current_location=None,
        total_experience=None,
    )
    user = SimpleNamespace(
        first_name="Asha",
        last_name="Rao",
        email="asha@example.com",
        mobile_number=None,
        profile_image_url=None,
    )

    result = EmployerDashboardService._build_interview_row(
        (interview, application, job, candidate, user)
    )

    assert result.scheduled_at == datetime(2026, 8, 6, 14, 30)
    assert result.location_or_link == "https://meet.example.com/1"


def test_employer_analytics_controller_success():
    async def run_test():
        payload = {
            "user_id": str(USER_ID),
            "email": "employer@example.com",
            "roles": [{"role_code": "ROLE_EMPLOYER"}],
        }
        with patch(
            "app.controller.employer_controller.dashboard.EmployerDashboardService.get_analytics",
            new_callable=AsyncMock,
            return_value=DumpableResult(stat_cards=[{"key": "applications", "value": 4}]),
        ) as service:
            response = await get_employer_analytics(
                from_date=date(2026, 7, 1),
                to_date=date(2026, 7, 3),
                job_id="job-1",
                period="weekly",
                department="Engineering",
                employment_type="FULL_TIME",
                location="Hyderabad",
                hiring_manager=str(USER_ID),
                status="PUBLISHED",
                payload=payload,
                session=FakeSession(),
            )

        assert response.message == "Employer analytics fetched successfully."
        assert response.data == {"stat_cards": [{"key": "applications", "value": 4}]}
        _, kwargs = service.call_args
        filters = kwargs["filters"]
        assert filters.from_date == date(2026, 7, 1)
        assert filters.to_date == date(2026, 7, 3)
        assert filters.job_id == "job-1"
        assert filters.period == "weekly"
        assert filters.department == "Engineering"
        assert filters.employment_type == "FULL_TIME"
        assert filters.location == "Hyderabad"
        assert filters.hiring_manager == str(USER_ID)
        assert filters.status == "PUBLISHED"

    asyncio.run(run_test())


def test_employer_dashboard_service_builds_template_sections():
    async def run_test():
        now = utc_now_naive()
        employer = SimpleNamespace(
            id="emp-1",
            company_name="NMK Global",
            company_email="hr@nmk.com",
            company_mobile="9999999999",
            company_website="https://nmk.com",
            company_logo_url="/logo.png",
            industry="Technology",
            company_size="100-500",
            company_location="Hyderabad",
            verification_status="VERIFIED",
            is_verified=1,
        )
        company = SimpleNamespace(
            company_id="company-1",
            company_name="NMK Global Inc",
            website="https://jobs.nmk.com",
            logo_path="/company-logo.png",
            industry="Staffing",
            size="500-1000",
            location="Remote",
        )
        job = SimpleNamespace(
            job_id="job-1",
            title="Python Developer",
            status="PUBLISHED",
            location="Hyderabad",
            employment_type="FULL_TIME",
            work_mode="HYBRID",
            created_at=now - timedelta(days=2),
            application_deadline=now + timedelta(days=15),
            no_of_openings=2,
        )
        candidate = SimpleNamespace(
            candidate_id="candidate-1",
            user_id=uuid4(),
            headline="Backend Engineer",
            current_location="Pune",
            total_experience=3.5,
        )
        user = SimpleNamespace(
            first_name="Asha",
            last_name="Rao",
            email="asha@example.com",
            mobile_number="8888888888",
            profile_image_url="/asha.png",
        )
        application = SimpleNamespace(
            application_id="app-1",
            application_status="APPLIED",
            applied_at=now,
            source="DIRECT",
        )
        interview = SimpleNamespace(
            interview_id="int-1",
            interview_date=(now + timedelta(days=1)).date(),
            interview_time=time(10, 30),
            mode="VIDEO",
            meeting_link="https://meet.example.com/1",
            interview_location=None,
            interviewer_name="Ravi",
            status="SCHEDULED",
        )
        audit = SimpleNamespace(
            audit_id=9,
            event_type="JOB_CREATED",
            message="Job created successfully",
            created_at=now,
            job_id="job-1",
        )

        with patch.multiple(
            "app.service.employer_service.dashboard_service.EmployerDashboardRepo",
            fetch_employer_profile=AsyncMock(return_value=employer),
            fetch_company_profile=AsyncMock(return_value=company),
            fetch_stat_counts=AsyncMock(
                return_value={
                    "total_jobs": 4,
                    "active_jobs": 2,
                    "total_applications": 7,
                    "pending_applications": 3,
                    "shortlisted_candidates": 2,
                    "scheduled_interviews": 1,
                    "unread_messages": 5,
                    "total_views": 40,
                }
            ),
            fetch_application_status_counts=AsyncMock(return_value=[("APPLIED", 3)]),
            fetch_job_status_counts=AsyncMock(return_value=[("PUBLISHED", 2)]),
            fetch_applications_over_time=AsyncMock(return_value=[(date(2026, 6, 19), 3)]),
            fetch_job_stage_counts=AsyncMock(
                return_value=[
                    (job, "APPLIED", 3),
                    (job, "SHORTLISTED", 2),
                ]
            ),
            fetch_job_stage_transition_counts=AsyncMock(
                return_value=[
                    (job, "APPLIED", "SHORTLISTED", 2),
                ]
            ),
            fetch_recent_applications=AsyncMock(return_value=[(application, job, candidate, user)]),
            fetch_active_jobs=AsyncMock(return_value=[(job, 7, 2, 40)]),
            fetch_upcoming_interviews=AsyncMock(return_value=[(interview, application, job, candidate, user)]),
            fetch_recent_activity=AsyncMock(return_value=[(audit, job)]),
            fetch_job_filter_options=AsyncMock(return_value=[job]),
        ):
            dashboard = await EmployerDashboardService.get_dashboard(
                session=FakeSession(),
                payload={
                    "user_id": str(USER_ID),
                    "roles": [{"role_code": "ROLE_EMPLOYER"}],
                },
                filters=EmployerDashboardFilters(limit=5),
            )

        assert dashboard.company_summary.company_name == "NMK Global Inc"
        assert {card.key: card.value for card in dashboard.stat_cards}["applications"] == 7
        assert dashboard.statistics.application_status[0].status == "APPLIED"
        assert dashboard.statistics.application_status[0].count == 3
        assert dashboard.statistics.job_status[1].status == "PUBLISHED"
        assert dashboard.statistics.job_status[1].count == 2
        assert dashboard.recent_applications[0].candidate.full_name == "Asha Rao"
        assert dashboard.active_jobs[0].applications_count == 7
        assert dashboard.job_stage_analytics[0].job.job_id == "job-1"
        assert dashboard.job_stage_analytics[0].total_applications == 5
        assert dashboard.job_stage_analytics[0].stage_counts[-1].status == "SHORTLISTED"
        assert dashboard.job_stage_analytics[0].stage_counts[-1].count == 2
        assert dashboard.job_stage_analytics[0].stage_transitions[0].from_status == "APPLIED"
        assert dashboard.job_stage_analytics[0].stage_transitions[0].to_status == "SHORTLISTED"
        assert "SHORTLISTED" in dashboard.filter_options.statuses
        assert dashboard.upcoming_interviews[0].scheduled_at == datetime.combine(
            interview.interview_date,
            interview.interview_time,
        )
        assert dashboard.upcoming_interviews[0].location_or_link == "https://meet.example.com/1"
        assert dashboard.upcoming_interviews[0].interviewer_name == "Ravi"
        assert dashboard.recent_activity[0].activity_type == "JOB_CREATED"
        assert dashboard.recent_activity[0].message == 'Created job "Python Developer"'
        assert dashboard.recent_activity[0].description == 'Created job "Python Developer"'
        assert dashboard.recent_activity[0].title == "Python Developer"
        assert dashboard.recent_activity[0].created_at == now
        assert dashboard.recent_activity[0].happened_at == now
        assert dashboard.filter_options.jobs[0].job_id == "job-1"
        assert dashboard.package_summary.posted_jobs_used == 4

    asyncio.run(run_test())


def test_employer_analytics_service_builds_spec_payload():
    async def run_test():
        now = utc_now_naive()
        employer = SimpleNamespace(id="emp-1")
        job = SimpleNamespace(
            job_id="job-1",
            title="Python Developer",
            status="PUBLISHED",
            created_at=now,
            application_deadline=None,
        )

        with patch.multiple(
            "app.service.employer_service.dashboard_service.EmployerDashboardRepo",
            fetch_employer_profile=AsyncMock(return_value=employer),
            fetch_job_filter_options=AsyncMock(return_value=[job]),
            fetch_analytics_stat_counts=AsyncMock(
                return_value={
                    "active_jobs": 1,
                    "applications": 4,
                    "shortlisted": 2,
                    "interviews": 1,
                    "profile_views": 20,
                }
            ),
            fetch_applications_over_time=AsyncMock(
                return_value=[(date(2026, 7, 1), 2), (date(2026, 7, 3), 1)]
            ),
            fetch_analytics_stage_events=AsyncMock(
                return_value=[
                    ("app-1", "APPLIED"),
                    ("app-1", "REVIEW"),
                    ("app-1", "SHORTLISTED"),
                    ("app-2", "OFFER"),
                    ("app-3", "APPLIED"),
                ]
            ),
            fetch_analytics_candidate_sources=AsyncMock(
                return_value=[("DIRECT_SEARCH", 3), ("JOB_BOARD", 1)]
            ),
            fetch_analytics_top_jobs=AsyncMock(return_value=[(job, 4, 2, 20)]),
            fetch_analytics_hire_milestones=AsyncMock(
                return_value=[
                    (datetime(2026, 7, 1), datetime(2026, 7, 11)),
                    (datetime(2026, 7, 2), datetime(2026, 7, 8)),
                ]
            ),
            fetch_analytics_overview_counts=AsyncMock(
                return_value={
                    "total_jobs": 1,
                    "active_jobs": 1,
                    "closed_jobs": 0,
                    "draft_jobs": 0,
                    "expired_jobs": 0,
                    "paused_jobs": 0,
                    "applications_received": 4,
                    "applications_today": 0,
                    "applications_this_week": 4,
                    "applications_this_month": 4,
                    "candidates_shortlisted": 2,
                    "candidates_rejected": 0,
                    "candidates_hired": 1,
                    "interviews_scheduled": 1,
                    "interviews_completed": 1,
                    "offers_released": 1,
                    "offers_accepted": 1,
                }
            ),
            fetch_analytics_job_rows=AsyncMock(
                return_value=[(job, 20, 4, 1, 2, 0, 1, 1)]
            ),
            fetch_analytics_application_events=AsyncMock(
                return_value=[
                    ("app-1", datetime(2026, 7, 1), "DIRECT_SEARCH", "SHORTLISTED"),
                    ("app-2", datetime(2026, 7, 3), "JOB_BOARD", "OFFER"),
                ]
            ),
            fetch_analytics_interview_events=AsyncMock(return_value=[]),
            fetch_analytics_candidate_rows=AsyncMock(return_value=[]),
            fetch_analytics_application_milestones=AsyncMock(
                return_value=[
                    ("app-1", "job-1", datetime(2026, 7, 1), "SHORTLISTED", datetime(2026, 7, 2)),
                    ("app-2", "job-1", datetime(2026, 7, 2), "HIRED", datetime(2026, 7, 8)),
                ]
            ),
        ):
            analytics = await EmployerDashboardService.get_analytics(
                session=FakeSession(),
                payload={
                    "user_id": str(USER_ID),
                    "roles": [{"role_code": "ROLE_EMPLOYER"}],
                },
                filters=EmployerAnalyticsFilters(
                    from_date=date(2026, 7, 1),
                    to_date=date(2026, 7, 3),
                    job_id="job-1",
                ),
            )

        stat_cards = {card.key: card.value for card in analytics.stat_cards}
        assert stat_cards["applications"] == 4
        assert stat_cards["avg_time_to_hire_days"] == 8
        assert [point.applications for point in analytics.applications_over_time] == [2, 0, 1]
        assert analytics.hiring_funnel[0].stage == "APPLIED"
        assert [stage.count for stage in analytics.hiring_funnel] == [3, 2, 2, 1, 1]
        assert analytics.candidate_source[0].percent == 75
        assert analytics.candidate_source[1].percent == 25
        assert analytics.top_jobs[0].conversion_rate == 50.0
        assert analytics.filter_options.jobs[0].title == "Python Developer"
        assert analytics.overview_metrics.total_jobs == 1
        assert analytics.job_analytics[0].average_time_to_shortlist == 3.5
        assert analytics.application_analytics.application_trends[0].applications == 1
        assert analytics.hiring_pipeline[0].label == "Applied"
        assert analytics.interview_analytics.scheduled == 0
        assert analytics.candidate_analytics.freshers == 0
        assert analytics.job_performance.most_applied_jobs[0].job_id == "job-1"
        assert "application_trends" in analytics.chart_data.line_charts

    asyncio.run(run_test())


def test_employer_dashboard_activity_mapper_hides_raw_delete_metadata():
    now = datetime(2026, 7, 20, 4, 7, 19, 896421)
    audit = SimpleNamespace(
        audit_id=10,
        event_type="JOB_DELETED",
        message=(
            "deleted_job_id=f65a0719-5079-4612-bd2c-f2deca9e21af; "
            "title=java developer jdbc; status=DRAFT; "
            "timestamp=2026-07-20T04:07:19.896421"
        ),
        created_at=now,
        job_id="",
    )

    activity = EmployerDashboardService._build_activity_row(audit)

    assert activity.activity_type == "JOB_DELETED"
    assert activity.message == 'Deleted job "Java Developer JDBC"'
    assert activity.description == 'Deleted job "Java Developer JDBC"'
    assert activity.title == "Java Developer JDBC"
    assert activity.status == "Draft"
    assert activity.created_at == now
    assert activity.happened_at == now
    assert activity.job_id is None


def test_employer_dashboard_service_rejects_candidate_role():
    async def run_test():
        with pytest.raises(HTTPException) as exc:
            await EmployerDashboardService.get_dashboard(
                session=FakeSession(),
                payload={
                    "user_id": str(USER_ID),
                    "roles": [{"role_code": "ROLE_CANDIDATE"}],
                },
                filters=EmployerDashboardFilters(),
            )

        assert exc.value.status_code == 403

    asyncio.run(run_test())


def test_employer_dashboard_service_validates_date_range():
    async def run_test():
        with pytest.raises(HTTPException) as exc:
            await EmployerDashboardService.get_dashboard(
                session=FakeSession(),
                payload={
                    "user_id": str(USER_ID),
                    "roles": [{"role_code": "ROLE_EMPLOYER"}],
                },
                filters=EmployerDashboardFilters(
                    date_from=date(2026, 6, 19),
                    date_to=date(2026, 6, 1),
                ),
            )

        assert exc.value.status_code == 400

    asyncio.run(run_test())
