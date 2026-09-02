from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.service.super_admin.analytics_service import SuperAdminAnalyticsService


class FakeSession:
    pass


def test_dashboard_analytics_includes_missing_widget_support():
    async def run_test():
        with patch.multiple(
            "app.service.super_admin.analytics_service.SuperAdminAnalyticsRepository",
            normalize_range=lambda range_filter: range_filter,
            count_users_by_roles=AsyncMock(
                return_value={
                    "ROLE_CANDIDATE": 10,
                    "ROLE_EMPLOYER": 4,
                    "ROLE_ADMIN": 2,
                }
            ),
            count_total_users=AsyncMock(return_value=16),
            get_job_counts=AsyncMock(
                return_value={
                    "total_jobs": 20,
                    "active_jobs": 8,
                    "inactive_jobs": 3,
                    "closed_jobs": 5,
                    "draft_jobs": 4,
                    "expired_jobs": 1,
                }
            ),
            monthly_registrations=AsyncMock(
                return_value=[SimpleNamespace(month="2026-07", count=6)]
            ),
            monthly_jobs_posted=AsyncMock(
                return_value=[SimpleNamespace(month="2026-07", count=7)]
            ),
            monthly_jobs_closed=AsyncMock(
                return_value=[SimpleNamespace(month="2026-07", count=2)]
            ),
            applications_over_time=AsyncMock(
                return_value=[SimpleNamespace(month="2026-07", count=9)]
            ),
            application_counts=AsyncMock(return_value={"total_applications": 11}),
            application_status_counts=AsyncMock(
                return_value={
                    "APPLIED": 5,
                    "SHORTLISTED": 2,
                    "INTERVIEW_SCHEDULED": 1,
                    "HIRED": 1,
                    "REJECTED": 2,
                }
            ),
            company_verification_counts=AsyncMock(
                return_value={
                    "approved_companies": 3,
                    "pending_companies": 2,
                    "rejected_companies": 1,
                }
            ),
            subscription_status_counts=AsyncMock(
                return_value={
                    "candidate_subscriptions": 8,
                    "admin_subscriptions": 2,
                    "active_candidate_plans": 6,
                    "expired_candidate_plans": 2,
                    "active_admin_plans": 1,
                    "expired_admin_plans": 1,
                }
            ),
            count_companies=AsyncMock(return_value=6),
            count_subscriptions=AsyncMock(return_value=7),
            job_status_counts=AsyncMock(
                return_value={"ACTIVE": 8, "DRAFT": 4, "CLOSED": 5}
            ),
        ):
            result = await SuperAdminAnalyticsService.get_dashboard_analytics(
                session=FakeSession(),
                months=12,
                range_filter="last_30_days",
            )

        assert result.total_users == 16
        assert result.total_inactive_jobs == 3
        assert result.jobs_posted_trend[0].count == 7
        assert result.jobs_closed_trend[0].count == 2
        assert result.total_applications == 11
        assert {item.status: item.count for item in result.application_funnel} == {
            "APPLIED": 5,
            "SHORTLISTED": 2,
            "INTERVIEW_SCHEDULED": 1,
            "OFFER": 0,
            "HIRED": 1,
            "REJECTED": 2,
        }
        assert result.approved_companies == 3
        assert result.pending_companies == 2
        assert result.rejected_companies == 1
        assert result.active_candidate_plans == 6
        assert result.expired_admin_plans == 1

    asyncio.run(run_test())


def test_registration_trends_reuses_existing_endpoint_with_range_alias():
    async def run_test():
        monthly_registrations = AsyncMock(
            return_value=[SimpleNamespace(month="2026-07-29", count=3)]
        )
        with patch.multiple(
            "app.service.super_admin.analytics_service.SuperAdminAnalyticsRepository",
            normalize_range=lambda range_filter: range_filter,
            monthly_registrations=monthly_registrations,
        ):
            result = await SuperAdminAnalyticsService.get_registration_trends(
                session=FakeSession(),
                months=12,
                range_filter="last_7_days",
            )

        monthly_registrations.assert_awaited_once()
        _, kwargs = monthly_registrations.call_args
        assert kwargs["months"] == 7
        assert kwargs["range_filter"] == "last_7_days"
        assert result.monthly_registrations == result.registration_trend
        assert result.registration_trend[0].month == "2026-07-29"

    asyncio.run(run_test())
