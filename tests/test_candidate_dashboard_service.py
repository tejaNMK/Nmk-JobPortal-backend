import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.service.candidate_dashboard_service import CandidateDashboardService


class FakeSession:
    pass


def test_candidate_dashboard_includes_withdrawn_status_and_total_cv_count():
    async def run_test():
        user_id = uuid4()
        profile = SimpleNamespace(
            candidate_id="candidate-1",
            current_location="Hyderabad",
            open_to_work=True,              # fixed: was searchable_flag (old field name)
            profile_visibility="PUBLIC",
            headline="Backend Developer",
            profile_completion_pct=80,
            active_resume_id="resume-1",
        )
        user = SimpleNamespace(
            user_id=user_id,
            first_name="Sai",
            last_name="Kiran",
            email="sai@example.com",
            mobile_number="9876543210",
            profile_image_url=None,
            cover_image_url=None,           # added: service reads user.cover_image_url
        )

        with patch.multiple(
            "app.service.candidate_dashboard_service.DashboardRepo",
            fetch_profile_and_user=AsyncMock(return_value=(profile, user)),
            fetch_cv_count=AsyncMock(return_value=3),
            fetch_unread_message_count=AsyncMock(return_value=2),
            fetch_profile_views_count=AsyncMock(return_value=10),           # added
            fetch_followings_count=AsyncMock(return_value=4),               # added
            fetch_application_stats=AsyncMock(return_value=[("APPLIED", 4), ("WITHDRAWN", 1)]),
            fetch_recent_applications=AsyncMock(return_value=[]),
            fetch_recommendations=AsyncMock(return_value=[]),
            fetch_companies_by_employer_ids=AsyncMock(return_value={}),
            fetch_followings=AsyncMock(return_value=[]),                    # added
            fetch_open_jobs_count_by_company=AsyncMock(return_value={}),    # added
        ), patch(
            "app.service.candidate_dashboard_service.CandidateJobRecommendationService.get_recommended_jobs",
            new=AsyncMock(return_value=None),
        ):
            dashboard = await CandidateDashboardService.get_dashboard(FakeSession(), user_id)

        # Stat bar
        assert dashboard.stat_bar.cv_list == 3
        assert dashboard.stat_bar.messages == 2
        assert dashboard.stat_bar.profile_views == 10
        assert dashboard.stat_bar.followings == 4

        # Profile summary — sidebar fields
        assert dashboard.profile_summary.email == "sai@example.com"
        assert dashboard.profile_summary.open_to_work is True
        assert dashboard.profile_summary.open_to_work_label == "Visible to recruiters"
        assert dashboard.profile_summary.name == "Sai Kiran"
        assert dashboard.profile_summary.cover is None

        # Application stats
        breakdown = {item.status: item.count for item in dashboard.application_stats.breakdown}
        assert breakdown["APPLIED"] == 4
        assert breakdown["WITHDRAWN"] == 1
        assert dashboard.application_stats.total == 5

    asyncio.run(run_test())


def test_dashboard_triggers_recommendation_generation_and_surfaces_results():
    
    async def run_test():
        user_id = uuid4()
        profile = SimpleNamespace(
            candidate_id="candidate-3",
            current_location="Bengaluru",
            open_to_work=True,
            profile_visibility="PUBLIC",
            headline="Frontend Developer",
            profile_completion_pct=90,
            active_resume_id="resume-3",
        )
        user = SimpleNamespace(
            user_id=user_id,
            first_name="Asha",
            last_name="Rao",
            email="asha@example.com",
            mobile_number="9998887777",
            profile_image_url=None,
            cover_image_url=None,
        )

        job = SimpleNamespace(
            job_id="job-1",
            title="React Developer",
            location="Bengaluru",
            work_mode="REMOTE",
            employment_type="FULL_TIME",
            salary_min=None,
            salary_max=None,
            salary_currency="USD",
            salary_period="Monthly",
            created_at=datetime(2026, 1, 1),
            employer_id="employer-1",
        )
        recommendation_row = SimpleNamespace(
            recommendation_id="rec-1",
            match_score=87.5,
            generated_at=datetime(2026, 1, 2),
            job=job,
        )

        recommend_mock = AsyncMock(return_value=None)
        with patch.multiple(
            "app.service.candidate_dashboard_service.DashboardRepo",
            fetch_profile_and_user=AsyncMock(return_value=(profile, user)),
            fetch_cv_count=AsyncMock(return_value=1),
            fetch_unread_message_count=AsyncMock(return_value=0),
            fetch_profile_views_count=AsyncMock(return_value=5),
            fetch_followings_count=AsyncMock(return_value=1),
            fetch_application_stats=AsyncMock(return_value=[]),
            fetch_recent_applications=AsyncMock(return_value=[]),
            fetch_recommendations=AsyncMock(return_value=[recommendation_row]),
            fetch_companies_by_employer_ids=AsyncMock(return_value={}),
            fetch_followings=AsyncMock(return_value=[]),
            fetch_open_jobs_count_by_company=AsyncMock(return_value={}),
        ), patch(
            "app.service.candidate_dashboard_service.CandidateJobRecommendationService.get_recommended_jobs",
            new=recommend_mock,
        ):
            dashboard = await CandidateDashboardService.get_dashboard(FakeSession(), user_id)

        # The AI engine must actually be invoked, keyed off this candidate's user_id.
        recommend_mock.assert_awaited_once()
        args, kwargs = recommend_mock.call_args
        assert args[1] == user_id

        # And its (persisted) results must flow through to the response.
        assert len(dashboard.job_recommendations) == 1
        assert dashboard.job_recommendations[0].recommendation_id == "rec-1"
        assert dashboard.job_recommendations[0].job.title == "React Developer"

    asyncio.run(run_test())


def test_open_to_work_false_shows_not_visible_label():
    """When open_to_work is False the sidebar label must say 'Not visible to recruiters'."""
    async def run_test():
        user_id = uuid4()
        profile = SimpleNamespace(
            candidate_id="candidate-2",
            current_location="Chennai",
            open_to_work=False,
            profile_visibility="PRIVATE",
            headline=None,
            profile_completion_pct=40,
            active_resume_id=None,
        )
        user = SimpleNamespace(
            user_id=user_id,
            first_name="Test",
            last_name=None,
            email="test@example.com",
            mobile_number=None,
            profile_image_url=None,
            cover_image_url=None,
        )

        with patch.multiple(
            "app.service.candidate_dashboard_service.DashboardRepo",
            fetch_profile_and_user=AsyncMock(return_value=(profile, user)),
            fetch_cv_count=AsyncMock(return_value=0),
            fetch_unread_message_count=AsyncMock(return_value=0),
            fetch_profile_views_count=AsyncMock(return_value=0),
            fetch_followings_count=AsyncMock(return_value=0),
            fetch_application_stats=AsyncMock(return_value=[]),
            fetch_recent_applications=AsyncMock(return_value=[]),
            fetch_recommendations=AsyncMock(return_value=[]),
            fetch_companies_by_employer_ids=AsyncMock(return_value={}),
            fetch_followings=AsyncMock(return_value=[]),
            fetch_open_jobs_count_by_company=AsyncMock(return_value={}),
        ), patch(
            "app.service.candidate_dashboard_service.CandidateJobRecommendationService.get_recommended_jobs",
            new=AsyncMock(return_value=None),
        ):
            dashboard = await CandidateDashboardService.get_dashboard(FakeSession(), user_id)

        assert dashboard.profile_summary.open_to_work is False
        assert dashboard.profile_summary.open_to_work_label == "Not visible to recruiters"
        assert dashboard.profile_summary.name == "Test"   # no last name

    asyncio.run(run_test())