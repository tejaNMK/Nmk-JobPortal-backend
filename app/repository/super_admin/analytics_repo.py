from datetime import datetime, timedelta
from app.utils.utc import utc_now_naive

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.authentication.role import Role
from app.model.authentication.users import Users
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.job import Job
from app.model.subscription.subscription import Subscription
from app.model.subscription.user_subscription import UserSubscription
from app.utils.date_range import NormalizedDateRange, normalize_datetime_for_db


class SuperAdminAnalyticsRepository:
    RANGE_DAYS = {
        "last_7_days": 7,
        "last_30_days": 30,
        "last_90_days": 90,
        "last_6_months": 183,
        "last_12_months": 365,
    }

    @staticmethod
    def normalize_range(range_filter: str | None) -> str | None:
        if not range_filter:
            return None
        normalized = range_filter.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "7_days": "last_7_days",
            "30_days": "last_30_days",
            "90_days": "last_90_days",
            "6_months": "last_6_months",
            "12_months": "last_12_months",
            "all": "all_time",
            "alltime": "all_time",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _trend_parts(
        column,
        range_filter: str | None,
        date_range: NormalizedDateRange | None = None,
    ):
        if date_range is not None:
            local_column = func.timezone(date_range.timezone, column)
            if date_range.grouping == "daily":
                trunc = func.date_trunc("day", local_column)
                label_format = "YYYY-MM-DD"
            elif date_range.grouping == "weekly":
                trunc = func.date_trunc("week", local_column)
                label_format = "YYYY-MM-DD"
            else:
                trunc = func.date_trunc("month", local_column)
                label_format = "YYYY-MM"
            return (
                trunc,
                label_format,
                normalize_datetime_for_db(date_range.utc_start),
                normalize_datetime_for_db(date_range.utc_end_exclusive),
                None,
            )

        normalized = SuperAdminAnalyticsRepository.normalize_range(range_filter)
        if normalized in ("last_7_days", "last_30_days", "last_90_days"):
            trunc = func.date_trunc("day", column)
            label_format = "YYYY-MM-DD"
        else:
            trunc = func.date_trunc("month", column)
            label_format = "YYYY-MM"

        cutoff = None
        if normalized in SuperAdminAnalyticsRepository.RANGE_DAYS:
            cutoff = utc_now_naive() - timedelta(
                days=SuperAdminAnalyticsRepository.RANGE_DAYS[normalized]
            )

        return trunc, label_format, cutoff, None, normalized

    @staticmethod
    async def count_total_users(session: AsyncSession) -> int:
        count = await session.scalar(
            select(func.count(Users.user_id)).where(Users.deleted_flag.is_(False))
        )
        return count or 0

    @staticmethod
    async def count_users_by_roles(session: AsyncSession) -> dict[str, int]:
        result = await session.execute(
            select(Role.role_code, func.count(distinct(Users.user_id)))
            .select_from(Users)
            .join(Users.roles)
            .where(
                Users.deleted_flag.is_(False),
                Role.role_code.in_(("ROLE_CANDIDATE", "ROLE_EMPLOYER", "ROLE_ADMIN")),
            )
            .group_by(Role.role_code)
        )
        return {role_code: count or 0 for role_code, count in result.all()}

    @staticmethod
    async def count_users_by_role(session: AsyncSession, role_code: str) -> int:
        count = await session.scalar(
            select(func.count(distinct(Users.user_id)))
            .select_from(Users)
            .join(Users.roles)
            .where(
                Users.deleted_flag.is_(False),
                Role.role_code == role_code,
            )
        )
        return count or 0

    @staticmethod
    async def get_job_counts(session: AsyncSession) -> dict[str, int]:
        now = utc_now_naive()
        result = await session.execute(
            select(
                func.count(Job.job_id).label("total_jobs"),
                func.count(
                    case(
                        (
                            and_(
                                Job.status == "PUBLISHED",
                                or_(
                                    Job.application_deadline.is_(None),
                                    Job.application_deadline >= now,
                                ),
                            ),
                            Job.job_id,
                        )
                    )
                ).label("active_jobs"),
                func.count(case((Job.status == "INACTIVE", Job.job_id))).label("inactive_jobs"),
                func.count(
                    case(
                        (
                            or_(Job.status == "CLOSED", Job.closed_at.is_not(None)),
                            Job.job_id,
                        )
                    )
                ).label("closed_jobs"),
                func.count(case((Job.status == "DRAFT", Job.job_id))).label("draft_jobs"),
                func.count(
                    case((Job.application_deadline < now, Job.job_id))
                ).label("expired_jobs"),
            ).where(Job.is_deleted.is_(False))
        )
        row = result.one()
        return {
            "total_jobs": row.total_jobs or 0,
            "active_jobs": row.active_jobs or 0,
            "inactive_jobs": row.inactive_jobs or 0,
            "closed_jobs": row.closed_jobs or 0,
            "draft_jobs": row.draft_jobs or 0,
            "expired_jobs": row.expired_jobs or 0,
        }

    @staticmethod
    async def count_companies(session: AsyncSession) -> int:
        count = await session.scalar(select(func.count(CompanyProfile.id)))
        return count or 0

    @staticmethod
    async def count_subscriptions(session: AsyncSession) -> int:
        count = await session.scalar(
            select(func.count(Subscription.subscription_id)).where(
                Subscription.is_active.is_(True)
            )
        )
        return count or 0

    @staticmethod
    async def monthly_registrations(
        session: AsyncSession,
        months: int = 12,
        range_filter: str | None = None,
        date_range: NormalizedDateRange | None = None,
    ):
        period_trunc, label_format, cutoff, end_exclusive, normalized = (
            SuperAdminAnalyticsRepository._trend_parts(Users.created_at, range_filter, date_range)
        )
        query = (
            select(
                func.to_char(period_trunc, label_format).label("month"),
                func.count(Users.user_id).label("count"),
            )
            .where(Users.deleted_flag.is_(False))
        )
        if cutoff is not None:
            query = query.where(Users.created_at >= cutoff)
        if end_exclusive is not None:
            query = query.where(Users.created_at < end_exclusive)
        query = query.group_by(period_trunc).order_by(period_trunc.desc())
        if normalized != "all_time":
            query = query.limit(months)
        result = await session.execute(
            query
        )
        return list(reversed(result.all()))

    @staticmethod
    async def monthly_jobs_posted(
        session: AsyncSession,
        months: int = 12,
        range_filter: str | None = None,
        date_range: NormalizedDateRange | None = None,
    ):
        period_trunc, label_format, cutoff, end_exclusive, normalized = (
            SuperAdminAnalyticsRepository._trend_parts(Job.created_at, range_filter, date_range)
        )
        query = (
            select(
                func.to_char(period_trunc, label_format).label("month"),
                func.count(Job.job_id).label("count"),
            )
            .where(Job.is_deleted.is_(False))
        )
        if cutoff is not None:
            query = query.where(Job.created_at >= cutoff)
        if end_exclusive is not None:
            query = query.where(Job.created_at < end_exclusive)
        query = query.group_by(period_trunc).order_by(period_trunc.desc())
        if normalized != "all_time":
            query = query.limit(months)
        result = await session.execute(
            query
        )
        return list(reversed(result.all()))

    @staticmethod
    async def monthly_jobs_closed(
        session: AsyncSession,
        months: int = 12,
        range_filter: str | None = None,
        date_range: NormalizedDateRange | None = None,
    ):
        period_trunc, label_format, cutoff, end_exclusive, normalized = (
            SuperAdminAnalyticsRepository._trend_parts(Job.closed_at, range_filter, date_range)
        )
        query = (
            select(
                func.to_char(period_trunc, label_format).label("month"),
                func.count(Job.job_id).label("count"),
            )
            .where(
                Job.is_deleted.is_(False),
                or_(Job.status == "CLOSED", Job.closed_at.is_not(None)),
                Job.closed_at.is_not(None),
            )
        )
        if cutoff is not None:
            query = query.where(Job.closed_at >= cutoff)
        if end_exclusive is not None:
            query = query.where(Job.closed_at < end_exclusive)
        query = query.group_by(period_trunc).order_by(period_trunc.desc())
        if normalized != "all_time":
            query = query.limit(months)
        result = await session.execute(query)
        return list(reversed(result.all()))

    @staticmethod
    async def applications_over_time(
        session: AsyncSession,
        months: int = 12,
        range_filter: str | None = None,
        date_range: NormalizedDateRange | None = None,
    ):
        period_trunc, label_format, cutoff, end_exclusive, normalized = (
            SuperAdminAnalyticsRepository._trend_parts(JobApplication.applied_at, range_filter, date_range)
        )
        query = (
            select(
                func.to_char(period_trunc, label_format).label("month"),
                func.count(JobApplication.application_id).label("count"),
            )
            .where(JobApplication.is_deleted.is_(False))
        )
        if cutoff is not None:
            query = query.where(JobApplication.applied_at >= cutoff)
        if end_exclusive is not None:
            query = query.where(JobApplication.applied_at < end_exclusive)
        query = query.group_by(period_trunc).order_by(period_trunc.desc())
        if normalized != "all_time":
            query = query.limit(months)
        result = await session.execute(query)
        return list(reversed(result.all()))

    @staticmethod
    async def job_status_counts(session: AsyncSession) -> dict[str, int]:
        result = await session.execute(
            select(Job.status, func.count(Job.job_id))
            .where(Job.is_deleted.is_(False))
            .group_by(Job.status)
        )
        return {status: count or 0 for status, count in result.all() if status}

    @staticmethod
    async def application_counts(session: AsyncSession) -> dict[str, int]:
        result = await session.execute(
            select(
                func.count(JobApplication.application_id).label("total_applications"),
            ).where(JobApplication.is_deleted.is_(False))
        )
        row = result.one()
        return {"total_applications": row.total_applications or 0}

    @staticmethod
    async def application_status_counts(session: AsyncSession) -> dict[str, int]:
        result = await session.execute(
            select(
                JobApplication.application_status,
                func.count(JobApplication.application_id),
            )
            .where(JobApplication.is_deleted.is_(False))
            .group_by(JobApplication.application_status)
        )
        return {
            status: count or 0
            for status, count in result.all()
            if status
        }

    @staticmethod
    async def company_verification_counts(session: AsyncSession) -> dict[str, int]:
        result = await session.execute(
            select(CompanyProfile.verification_status, func.count(CompanyProfile.id))
            .group_by(CompanyProfile.verification_status)
        )
        counts = {
            (status or "").upper(): count or 0
            for status, count in result.all()
        }
        return {
            "approved_companies": counts.get("APPROVED", 0),
            "pending_companies": counts.get("PENDING", 0),
            "rejected_companies": counts.get("REJECTED", 0),
        }

    @staticmethod
    async def subscription_status_counts(session: AsyncSession) -> dict[str, int]:
        result = await session.execute(
            select(
                func.upper(UserSubscription.role).label("role"),
                UserSubscription.status,
                func.count(UserSubscription.user_subscription_id).label("count"),
            )
            .group_by(func.upper(UserSubscription.role), UserSubscription.status)
        )
        counts = {
            (role or "", status or ""): count or 0
            for role, status, count in result.all()
        }
        return {
            "candidate_subscriptions": sum(
                count for (role, _status), count in counts.items() if role == "CANDIDATE"
            ),
            "admin_subscriptions": sum(
                count for (role, _status), count in counts.items() if role == "ADMIN"
            ),
            "active_candidate_plans": counts.get(("CANDIDATE", "ACTIVE"), 0),
            "expired_candidate_plans": counts.get(("CANDIDATE", "EXPIRED"), 0),
            "active_admin_plans": counts.get(("ADMIN", "ACTIVE"), 0),
            "expired_admin_plans": counts.get(("ADMIN", "EXPIRED"), 0),
        }
