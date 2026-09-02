from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.super_admin.analytics_repo import SuperAdminAnalyticsRepository
from app.schema.super_admin.analytics import (
    ApplicationAnalyticsResponse,
    CompanyAnalyticsResponse,
    DashboardAnalyticsResponse,
    JobAnalyticsResponse,
    MonthlyCountItem,
    RegistrationTrendsResponse,
    StatusCountItem,
    SubscriptionAnalyticsResponse,
    UserDistributionResponse,
)
from app.utils.date_range import NormalizedDateRange


class SuperAdminAnalyticsService:
    APPLICATION_FUNNEL_STATUSES = (
        "APPLIED",
        "SHORTLISTED",
        "INTERVIEW_SCHEDULED",
        "OFFER",
        "HIRED",
        "REJECTED",
    )

    @staticmethod
    def _months_for_range(months: int, range_filter: str | None) -> int:
        normalized = SuperAdminAnalyticsRepository.normalize_range(range_filter)
        if normalized in ("last_7_days", "last_30_days", "last_90_days"):
            return {
                "last_7_days": 7,
                "last_30_days": 30,
                "last_90_days": 90,
            }[normalized]
        if normalized == "last_6_months":
            return 6
        if normalized == "last_12_months":
            return 12
        return months

    @staticmethod
    async def get_user_distribution(session: AsyncSession) -> UserDistributionResponse:
        counts = await SuperAdminAnalyticsRepository.count_users_by_roles(session)
        return UserDistributionResponse(
            total_users=await SuperAdminAnalyticsRepository.count_total_users(session),
            total_candidates=counts.get("ROLE_CANDIDATE", 0),
            total_employers=counts.get("ROLE_EMPLOYER", 0),
            total_admins=counts.get("ROLE_ADMIN", 0),
        )

    @staticmethod
    async def get_job_analytics(
        session: AsyncSession,
        months: int = 12,
        range_filter: str | None = None,
        date_range: NormalizedDateRange | None = None,
    ) -> JobAnalyticsResponse:
        trend_limit = SuperAdminAnalyticsService._months_for_range(months, range_filter)
        counts = await SuperAdminAnalyticsRepository.get_job_counts(session)
        jobs_posted = await SuperAdminAnalyticsRepository.monthly_jobs_posted(
            session=session,
            months=trend_limit,
            range_filter=range_filter,
            date_range=date_range,
        )
        jobs_closed = await SuperAdminAnalyticsRepository.monthly_jobs_closed(
            session=session,
            months=trend_limit,
            range_filter=range_filter,
            date_range=date_range,
        )
        status_counts = await SuperAdminAnalyticsRepository.job_status_counts(session)
        return JobAnalyticsResponse(
            total_jobs=counts["total_jobs"],
            active_jobs=counts["active_jobs"],
            inactive_jobs=counts["inactive_jobs"],
            closed_jobs=counts["closed_jobs"],
            draft_jobs=counts["draft_jobs"],
            expired_jobs=counts["expired_jobs"],
            status_counts=status_counts,
            jobs_posted_trend=SuperAdminAnalyticsService._trend_items(jobs_posted, date_range),
            jobs_closed_trend=SuperAdminAnalyticsService._trend_items(jobs_closed, date_range),
            **SuperAdminAnalyticsService._range_meta(date_range),
        )

    @staticmethod
    def _monthly_items(rows) -> list[MonthlyCountItem]:
        return [
            MonthlyCountItem(month=row.month, count=row.count or 0)
            for row in rows
        ]

    @staticmethod
    def _range_meta(date_range: NormalizedDateRange | None) -> dict:
        if date_range is None:
            return {}
        return {
            "grouping": date_range.grouping,
            "from_date": date_range.from_date.isoformat(),
            "to_date": date_range.to_date.isoformat(),
            "timezone": date_range.timezone,
        }

    @staticmethod
    def _period_labels(date_range: NormalizedDateRange | None) -> list[str]:
        if date_range is None:
            return []
        current = date_range.from_date
        labels: list[str] = []
        if date_range.grouping == "daily":
            while current <= date_range.to_date:
                labels.append(current.isoformat())
                current += timedelta(days=1)
            return labels
        if date_range.grouping == "weekly":
            current = current - timedelta(days=current.weekday())
            while current <= date_range.to_date:
                labels.append(current.isoformat())
                current += timedelta(days=7)
            return labels
        current = date(current.year, current.month, 1)
        while current <= date_range.to_date:
            labels.append(current.strftime("%Y-%m"))
            current = (
                date(current.year + 1, 1, 1)
                if current.month == 12
                else date(current.year, current.month + 1, 1)
            )
        return labels

    @staticmethod
    def _trend_items(rows, date_range: NormalizedDateRange | None) -> list[MonthlyCountItem]:
        labels = SuperAdminAnalyticsService._period_labels(date_range)
        if not labels:
            return SuperAdminAnalyticsService._monthly_items(rows)
        counts = {row.month: row.count or 0 for row in rows}
        return [
            MonthlyCountItem(month=label, count=counts.get(label, 0))
            for label in labels
        ]

    @staticmethod
    async def get_registration_trends(
        session: AsyncSession,
        months: int,
        range_filter: str | None = None,
        date_range: NormalizedDateRange | None = None,
    ) -> RegistrationTrendsResponse:
        trend_limit = SuperAdminAnalyticsService._months_for_range(months, range_filter)
        rows = await SuperAdminAnalyticsRepository.monthly_registrations(
            session=session,
            months=trend_limit,
            range_filter=range_filter,
            date_range=date_range,
        )
        items = SuperAdminAnalyticsService._trend_items(rows, date_range)
        return RegistrationTrendsResponse(
            monthly_registrations=items,
            registration_trend=items,
            **SuperAdminAnalyticsService._range_meta(date_range),
        )

    @staticmethod
    async def get_application_analytics(
        session: AsyncSession,
        months: int,
        range_filter: str | None = None,
        date_range: NormalizedDateRange | None = None,
    ) -> ApplicationAnalyticsResponse:
        trend_limit = SuperAdminAnalyticsService._months_for_range(months, range_filter)
        totals = await SuperAdminAnalyticsRepository.application_counts(session)
        trend_rows = await SuperAdminAnalyticsRepository.applications_over_time(
            session=session,
            months=trend_limit,
            range_filter=range_filter,
            date_range=date_range,
        )
        status_counts = await SuperAdminAnalyticsRepository.application_status_counts(session)
        return ApplicationAnalyticsResponse(
            total_applications=totals["total_applications"],
            applications_trend=SuperAdminAnalyticsService._trend_items(trend_rows, date_range),
            application_funnel=[
                StatusCountItem(status=status, count=status_counts.get(status, 0))
                for status in SuperAdminAnalyticsService.APPLICATION_FUNNEL_STATUSES
            ],
            **SuperAdminAnalyticsService._range_meta(date_range),
        )

    @staticmethod
    async def get_company_analytics(session: AsyncSession) -> CompanyAnalyticsResponse:
        return CompanyAnalyticsResponse(
            **await SuperAdminAnalyticsRepository.company_verification_counts(session)
        )

    @staticmethod
    async def get_subscription_analytics(
        session: AsyncSession,
    ) -> SubscriptionAnalyticsResponse:
        return SubscriptionAnalyticsResponse(
            **await SuperAdminAnalyticsRepository.subscription_status_counts(session)
        )

    @staticmethod
    async def get_dashboard_analytics(
        session: AsyncSession,
        months: int,
        range_filter: str | None = None,
        date_range: NormalizedDateRange | None = None,
    ) -> DashboardAnalyticsResponse:
        trend_limit = SuperAdminAnalyticsService._months_for_range(months, range_filter)
        users = await SuperAdminAnalyticsService.get_user_distribution(session)
        jobs = await SuperAdminAnalyticsRepository.get_job_counts(session)
        registrations = await SuperAdminAnalyticsRepository.monthly_registrations(
            session=session,
            months=trend_limit,
            range_filter=range_filter,
            date_range=date_range,
        )
        jobs_posted = await SuperAdminAnalyticsRepository.monthly_jobs_posted(
            session=session,
            months=trend_limit,
            range_filter=range_filter,
            date_range=date_range,
        )
        jobs_closed = await SuperAdminAnalyticsRepository.monthly_jobs_closed(
            session=session,
            months=trend_limit,
            range_filter=range_filter,
            date_range=date_range,
        )
        applications = await SuperAdminAnalyticsService.get_application_analytics(
            session=session,
            months=trend_limit,
            range_filter=range_filter,
            date_range=date_range,
        )
        company_counts = await SuperAdminAnalyticsService.get_company_analytics(session)
        subscription_counts = await SuperAdminAnalyticsService.get_subscription_analytics(session)
        registration_items = SuperAdminAnalyticsService._trend_items(registrations, date_range)
        jobs_posted_items = SuperAdminAnalyticsService._trend_items(jobs_posted, date_range)
        jobs_closed_items = SuperAdminAnalyticsService._trend_items(jobs_closed, date_range)
        job_status_counts = await SuperAdminAnalyticsRepository.job_status_counts(session)
        return DashboardAnalyticsResponse(
            total_users=users.total_users,
            total_candidates=users.total_candidates,
            total_employers=users.total_employers,
            total_admins=users.total_admins,
            total_companies=await SuperAdminAnalyticsRepository.count_companies(session),
            total_jobs=jobs["total_jobs"],
            total_active_jobs=jobs["active_jobs"],
            total_inactive_jobs=jobs["inactive_jobs"],
            total_closed_jobs=jobs["closed_jobs"],
            total_draft_jobs=jobs["draft_jobs"],
            active_jobs=jobs["active_jobs"],
            inactive_jobs=jobs["inactive_jobs"],
            closed_jobs=jobs["closed_jobs"],
            draft_jobs=jobs["draft_jobs"],
            expired_jobs=jobs["expired_jobs"],
            total_subscriptions=await SuperAdminAnalyticsRepository.count_subscriptions(session),
            monthly_registrations=registration_items,
            registration_trend=registration_items,
            monthly_jobs_posted=jobs_posted_items,
            jobs_posted_trend=jobs_posted_items,
            monthly_jobs_closed=jobs_closed_items,
            jobs_closed_trend=jobs_closed_items,
            job_status_counts=job_status_counts,
            status_counts=job_status_counts,
            total_applications=applications.total_applications,
            applications_trend=applications.applications_trend,
            application_funnel=applications.application_funnel,
            approved_companies=company_counts.approved_companies,
            pending_companies=company_counts.pending_companies,
            rejected_companies=company_counts.rejected_companies,
            candidate_subscriptions=subscription_counts.candidate_subscriptions,
            admin_subscriptions=subscription_counts.admin_subscriptions,
            active_candidate_plans=subscription_counts.active_candidate_plans,
            expired_candidate_plans=subscription_counts.expired_candidate_plans,
            active_admin_plans=subscription_counts.active_admin_plans,
            expired_admin_plans=subscription_counts.expired_admin_plans,
            range=date_range.as_response() if date_range else None,
            current_totals={
                "total_users": users.total_users,
                "total_candidates": users.total_candidates,
                "total_employers": users.total_employers,
                "total_admins": users.total_admins,
                "total_jobs": jobs["total_jobs"],
                "active_jobs": jobs["active_jobs"],
                "inactive_jobs": jobs["inactive_jobs"],
                "closed_jobs": jobs["closed_jobs"],
                "draft_jobs": jobs["draft_jobs"],
            } if date_range else None,
            period_metrics={
                "registrations": sum(item.count for item in registration_items),
                "jobs_posted": sum(item.count for item in jobs_posted_items),
                "jobs_closed": sum(item.count for item in jobs_closed_items),
                "applications": sum(item.count for item in applications.applications_trend),
            } if date_range else None,
            grouping=date_range.grouping if date_range else None,
        )
