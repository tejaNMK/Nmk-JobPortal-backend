from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.activity_log import ActivityLog
from app.model.authentication.users import Users
from app.model.authentication.role import Role
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.job import Job
from app.model.subscription.user_subscription import UserSubscription
from app.utils.date_range import NormalizedDateRange, normalize_datetime_for_db


class DashboardRepository:

    @staticmethod
    async def get_dashboard_summary(
        session: AsyncSession,
        date_range: NormalizedDateRange | None = None,
    ):
        user_counts = await session.execute(
            select(
                func.count(distinct(Users.user_id)).label("total_users"),
                func.count(
                    distinct(
                        case(
                            (
                                Role.role_code == "ROLE_CANDIDATE",
                                Users.user_id,
                            )
                        )
                    )
                ).label("total_candidates"),
                func.count(
                    distinct(
                        case(
                            (
                                Role.role_code == "ROLE_EMPLOYER",
                                Users.user_id,
                            )
                        )
                    )
                ).label("total_employers"),
                func.count(
                    distinct(
                        case(
                            (
                                Role.role_code == "ROLE_ADMIN",
                                Users.user_id,
                            )
                        )
                    )
                ).label("total_admins"),
            )
            .select_from(Users)
            .outerjoin(Users.roles)
            .where(Users.deleted_flag.is_(False))
        )
        user_row = user_counts.one()

        candidate_profiles_count = (
            select(func.count(CandidateProfile.candidate_id))
            .where(CandidateProfile.is_deleted.is_(False))
            .scalar_subquery()
        )
        employer_profiles_count = (
            select(func.count(EmployerProfile.id))
            .where(EmployerProfile.is_deleted == 0)
            .scalar_subquery()
        )
        companies_count = select(func.count(CompanyProfile.id)).scalar_subquery()
        profile_counts = await session.execute(
            select(
                candidate_profiles_count.label("profiles_candidates"),
                employer_profiles_count.label("profiles_employers"),
                companies_count.label("total_companies"),
            )
        )
        profile_row = profile_counts.one()

        job_counts = await session.execute(
            select(
                func.count(Job.job_id).label("total_jobs"),
                func.count(case((Job.status == "PUBLISHED", Job.job_id))).label("active_jobs"),
                func.count(case((Job.status == "INACTIVE", Job.job_id))).label("inactive_jobs"),
                func.count(case((Job.status == "DRAFT", Job.job_id))).label("draft_jobs"),
                func.count(case(((Job.status == "CLOSED") | (Job.closed_at.is_not(None)), Job.job_id))).label("closed_jobs"),
            ).where(Job.is_deleted.is_(False))
        )
        job_row = job_counts.one()

        subscription_counts = await session.execute(
            select(
                func.count(
                    case(
                        (
                            (func.upper(UserSubscription.role) == "CANDIDATE")
                            & (UserSubscription.status == "ACTIVE"),
                            UserSubscription.user_subscription_id,
                        )
                    )
                ).label("candidate_subscriptions"),
                func.count(
                    case(
                        (
                            (func.upper(UserSubscription.role) == "ADMIN")
                            & (UserSubscription.status == "ACTIVE"),
                            UserSubscription.user_subscription_id,
                        )
                    )
                ).label("admin_subscriptions"),
            )
        )
        subscription_row = subscription_counts.one()

        current_totals = {
            "total_users": user_row.total_users or 0,
            "total_candidates": user_row.total_candidates or profile_row.profiles_candidates or 0,
            "total_employers": user_row.total_employers or profile_row.profiles_employers or 0,
            "total_admins": user_row.total_admins or 0,
            "total_jobs": job_row.total_jobs or 0,
            "active_jobs": job_row.active_jobs or 0,
            "inactive_jobs": job_row.inactive_jobs or 0,
            "draft_jobs": job_row.draft_jobs or 0,
            "closed_jobs": job_row.closed_jobs or 0,
            "total_companies": profile_row.total_companies or 0,
            "candidate_subscriptions": subscription_row.candidate_subscriptions or 0,
            "admin_subscriptions": subscription_row.admin_subscriptions or 0,
        }
        response = dict(current_totals)

        if date_range is not None:
            naive_start = normalize_datetime_for_db(date_range.utc_start)
            naive_end = normalize_datetime_for_db(date_range.utc_end_exclusive)
            period_counts = await session.execute(
                select(
                    func.count(distinct(Users.user_id)).label("new_users"),
                    func.count(
                        distinct(
                            case(
                                (
                                    Role.role_code == "ROLE_CANDIDATE",
                                    Users.user_id,
                                )
                            )
                        )
                    ).label("new_candidates"),
                    func.count(
                        distinct(
                            case(
                                (
                                    Role.role_code == "ROLE_EMPLOYER",
                                    Users.user_id,
                                )
                            )
                        )
                    ).label("new_employers"),
                )
                .select_from(Users)
                .outerjoin(Users.roles)
                .where(
                    Users.deleted_flag.is_(False),
                    Users.created_at >= naive_start,
                    Users.created_at < naive_end,
                )
            )
            period_user_row = period_counts.one()
            jobs_posted = await session.scalar(
                select(func.count(Job.job_id)).where(
                    Job.is_deleted.is_(False),
                    Job.created_at >= naive_start,
                    Job.created_at < naive_end,
                )
            )
            company_submissions = await session.scalar(
                select(func.count(CompanyProfile.id)).where(
                    CompanyProfile.created_at >= naive_start,
                    CompanyProfile.created_at < naive_end,
                )
            )
            subscriptions_created = await session.scalar(
                select(func.count(UserSubscription.user_subscription_id)).where(
                    UserSubscription.created_at >= naive_start,
                    UserSubscription.created_at < naive_end,
                )
            )
            activity_logs = await session.scalar(
                select(func.count(ActivityLog.id)).where(
                    ActivityLog.created_at >= date_range.utc_start,
                    ActivityLog.created_at < date_range.utc_end_exclusive,
                )
            )
            response.update(
                {
                    "range": date_range.as_response(),
                    "current_totals": current_totals,
                    "period_metrics": {
                        "new_users": period_user_row.new_users or 0,
                        "new_candidates": period_user_row.new_candidates or 0,
                        "new_employers": period_user_row.new_employers or 0,
                        "jobs_posted": jobs_posted or 0,
                        "company_approval_submissions": company_submissions or 0,
                        "subscriptions_created": subscriptions_created or 0,
                        "activity_logs": activity_logs or 0,
                    },
                }
            )

        return response
