from datetime import date, datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import Date, Text, and_, case, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.model.activity_log import ActivityLog
from app.model.authentication.role import Role
from app.model.authentication.users import Users
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job
from app.model.subscription.subscription import Subscription
from app.model.subscription.user_subscription import UserSubscription
from app.utils.date_range import (
    NormalizedDateRange,
    normalize_datetime_for_db,
    normalize_to_utc,
)


class SuperAdminDashboardRepository:
    @staticmethod
    async def list_recent_registrations(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        role: Optional[str] = None,
        date_range: NormalizedDateRange | None = None,
    ):
        query = (
            select(Users, Role)
            .join(Users.roles)
            .where(Users.deleted_flag.is_(False))
        )

        if role:
            role_code = role.upper()
            if not role_code.startswith("ROLE_"):
                role_code = f"ROLE_{role_code}"
            query = query.where(Role.role_code == role_code)

        search_value = search.strip() if search else ""
        if search_value:
            search_term = f"%{search_value}%"
            full_name = Users.first_name + " " + func.coalesce(Users.last_name, "")
            query = query.where(
                or_(
                    Users.first_name.ilike(search_term),
                    Users.last_name.ilike(search_term),
                    Users.email.ilike(search_term),
                    Users.mobile_number.ilike(search_term),
                    full_name.ilike(search_term),
                )
            )

        if date_range:
            start_at = normalize_datetime_for_db(date_range.utc_start)
            end_at = normalize_datetime_for_db(date_range.utc_end_exclusive)
            query = query.where(
                Users.created_at >= start_at,
                Users.created_at < end_at,
            )

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        result = await session.execute(
            query.order_by(Users.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return result.all(), total or 0

    @staticmethod
    async def get_job_overview(session: AsyncSession):
        now = utc_now_naive()
        today = date.today()

        overview = await session.execute(
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
                func.count(
                    case(
                        (
                            Job.status == "DRAFT",
                            Job.job_id,
                        )
                    )
                ).label("draft_jobs"),
                func.count(
                    case(
                        (
                            or_(Job.status == "CLOSED", Job.closed_at.is_not(None)),
                            Job.job_id,
                        )
                    )
                ).label("closed_jobs"),
                func.count(
                    case(
                        (
                            Job.application_deadline < now,
                            Job.job_id,
                        )
                    )
                ).label("expired_jobs"),
                func.count(case((Job.created_at >= datetime.combine(today, datetime.min.time()), Job.job_id))).label("jobs_posted_today"),
            ).where(Job.is_deleted.is_(False))
        )

        status_rows = await session.execute(
            select(Job.status, func.count(Job.job_id))
            .where(Job.is_deleted.is_(False))
            .group_by(Job.status)
        )

        row = overview.one()
        status_counts = {
            status: count or 0
            for status, count in status_rows.all()
            if status
        }

        return {
            "total_jobs": row.total_jobs or 0,
            "active_jobs": row.active_jobs or 0,
            "draft_jobs": row.draft_jobs or 0,
            "closed_jobs": row.closed_jobs or 0,
            "inactive_jobs": (status_counts.get("INACTIVE", 0) or 0),
            "expired_jobs": row.expired_jobs or 0,
            "jobs_posted_today": row.jobs_posted_today or 0,
            "total_records": row.total_jobs or 0,
            "status_counts": status_counts,
        }

    @staticmethod
    async def list_jobs(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        company: Optional[str] = None,
        recruiter: Optional[str] = None,
        location: Optional[str] = None,
        status: Optional[str] = None,
        employment_type: Optional[str] = None,
        work_mode: Optional[str] = None,
        experience_level: Optional[str] = None,
        industry: Optional[str] = None,
        salary_min: Optional[float] = None,
        salary_max: Optional[float] = None,
        posted_date: Optional[datetime] = None,
        expiry_date: Optional[datetime] = None,
        date_range: NormalizedDateRange | None = None,
        sort_by: str = "posted_date",
        sort_order: str = "desc",
    ):
        query = (
            select(Job, EmployerProfile, Users)
            .outerjoin(EmployerProfile, EmployerProfile.id == Job.employer_id)
            .outerjoin(Users, Users.user_id == EmployerProfile.user_id)
            .where(Job.is_deleted.is_(False))
        )

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Job.title.ilike(search_term),
                    Job.job_id.ilike(search_term),
                    Job.company_name.ilike(search_term),
                    EmployerProfile.company_name.ilike(search_term),
                    Users.first_name.ilike(search_term),
                    Users.last_name.ilike(search_term),
                    Users.email.ilike(search_term),
                )
            )

        if company:
            company_term = f"%{company}%"
            query = query.where(
                or_(
                    Job.company_name.ilike(company_term),
                    EmployerProfile.company_name.ilike(company_term),
                )
            )

        if recruiter:
            recruiter_term = f"%{recruiter}%"
            query = query.where(
                or_(
                    Users.first_name.ilike(recruiter_term),
                    Users.last_name.ilike(recruiter_term),
                    Users.email.ilike(recruiter_term),
                )
            )

        if location:
            query = query.where(Job.location.ilike(f"%{location}%"))

        if status:
            normalized_status = status.upper()
            if normalized_status == "EXPIRED":
                query = query.where(
                    or_(
                        Job.status == "EXPIRED",
                        Job.application_deadline < utc_now_naive(),
                    )
                )
            else:
                query = query.where(Job.status == normalized_status)

        if employment_type:
            query = query.where(Job.employment_type == employment_type.upper())

        if work_mode:
            query = query.where(Job.work_mode == work_mode.upper())

        if experience_level:
            query = query.where(
                or_(
                    cast(Job.experience_min, Text).ilike(f"%{experience_level}%"),
                    cast(Job.experience_max, Text).ilike(f"%{experience_level}%"),
                )
            )

        if industry:
            query = query.where(EmployerProfile.industry.ilike(f"%{industry}%"))

        if salary_min is not None:
            query = query.where(
                or_(Job.salary_max.is_(None), Job.salary_max >= salary_min)
            )

        if salary_max is not None:
            query = query.where(
                or_(Job.salary_min.is_(None), Job.salary_min <= salary_max)
            )

        if posted_date:
            query = query.where(cast(Job.created_at, Date) == posted_date.date())
        elif date_range:
            start_at = normalize_datetime_for_db(date_range.utc_start)
            end_at = normalize_datetime_for_db(date_range.utc_end_exclusive)
            query = query.where(
                Job.created_at >= start_at,
                Job.created_at < end_at,
            )

        if expiry_date:
            query = query.where(cast(Job.application_deadline, Date) == expiry_date.date())

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        sort_columns = {
            "job_title": Job.title,
            "company_name": Job.company_name,
            "recruiter_name": Users.first_name,
            "location": Job.location,
            "employment_type": Job.employment_type,
            "job_type": Job.employment_type,
            "work_mode": Job.work_mode,
            "industry": EmployerProfile.industry,
            "salary_min": Job.salary_min,
            "salary_max": Job.salary_max,
            "status": Job.status,
            "posted_date": Job.created_at,
            "expiry_date": Job.application_deadline,
            "created_at": Job.created_at,
        }
        sort_column = sort_columns.get(sort_by, Job.created_at)
        order_clause = (
            sort_column.asc()
            if sort_order.lower() == "asc"
            else sort_column.desc()
        )

        result = await session.execute(
            query.order_by(order_clause)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return result.all(), total or 0

    @staticmethod
    async def bulk_update_jobs(
        session: AsyncSession,
        job_ids: list[str],
        action: str,
        actor_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> int:
        now = utc_now_naive()
        values = {
            "updated_at": now,
            "updated_by": actor_id,
        }

        action = action.lower()
        if action == "activate":
            values.update({"status": "PUBLISHED", "closed_at": None, "closed_reason": None})
        elif action == "pause":
            values.update({"status": "INACTIVE"})
        elif action == "close":
            values.update({"status": "CLOSED", "closed_at": now, "closed_reason": reason})
        elif action == "delete":
            values.update({"is_deleted": True, "deleted_at": now})

        result = await session.execute(
            update(Job)
            .where(Job.job_id.in_(job_ids), Job.is_deleted.is_(False))
            .values(**values)
        )
        await session.commit()
        return int(result.rowcount or 0)

    @staticmethod
    async def list_users(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
        subscription: Optional[str] = None,
        registered_from: Optional[datetime] = None,
        registered_to: Optional[datetime] = None,
        date_range: NormalizedDateRange | None = None,
        sort_by: str = "newest",
    ):
        query = (
            select(Users, Subscription.subscription_name)
            .outerjoin(
                UserSubscription,
                (UserSubscription.user_id == Users.user_id)
                & (UserSubscription.status == "ACTIVE"),
            )
            .outerjoin(
                Subscription,
                Subscription.subscription_id == UserSubscription.subscription_id,
            )
            .options(selectinload(Users.roles))
            .where(Users.deleted_flag.is_(False))
        )

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Users.first_name.ilike(search_term),
                    Users.last_name.ilike(search_term),
                    Users.email.ilike(search_term),
                    Users.mobile_number.ilike(search_term),
                )
            )

        if role:
            role_code = role.upper()
            if not role_code.startswith("ROLE_"):
                role_code = f"ROLE_{role_code}"
            query = query.join(Users.roles)
            query = query.where(Role.role_code == role_code)

        if status:
            query = query.where(Users.user_status == status.upper())

        if subscription:
            query = query.where(
                Subscription.subscription_name.ilike(f"%{subscription}%")
            )

        if registered_from:
            query = query.where(Users.created_at >= normalize_datetime_for_db(registered_from))

        if registered_to:
            query = query.where(Users.created_at <= normalize_datetime_for_db(registered_to))
        elif date_range and not registered_from:
            start_at = normalize_datetime_for_db(date_range.utc_start)
            end_at = normalize_datetime_for_db(date_range.utc_end_exclusive)
            query = query.where(
                Users.created_at >= start_at,
                Users.created_at < end_at,
            )

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        if sort_by == "oldest":
            order_by = Users.created_at.asc()
        elif sort_by == "name":
            order_by = Users.first_name.asc()
        else:
            order_by = Users.created_at.desc()

        result = await session.execute(
            query.order_by(order_by)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return result.all(), total or 0


class ActivityLogRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        log: ActivityLog,
        commit: bool = True,
    ) -> ActivityLog:
        session.add(log)
        if commit:
            await session.commit()
        elif hasattr(session, "flush"):
            await session.flush()
        if hasattr(session, "refresh"):
            await session.refresh(log)
        return log

    @staticmethod
    async def list_logs(
        session: AsyncSession,
        page: int,
        page_size: int,
        action: Optional[str] = None,
        actor: Optional[str] = None,
        role: Optional[str] = None,
        entity_type: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date_range: NormalizedDateRange | None = None,
    ):
        query = select(ActivityLog, Users).outerjoin(
            Users,
            Users.user_id == ActivityLog.actor_id,
        )

        if action:
            query = query.where(ActivityLog.action == action.upper())

        if role:
            normalized_role = role.upper()
            if not normalized_role.startswith("ROLE_"):
                normalized_role = f"ROLE_{normalized_role}"
            query = query.where(ActivityLog.actor_role == normalized_role)

        if entity_type:
            query = query.where(ActivityLog.entity_type == entity_type)

        actor_query = actor or search
        if actor_query:
            actor_search = f"%{actor_query}%"
            query = query.where(
                or_(
                    ActivityLog.actor_id.cast(Text).ilike(actor_search),
                    Users.first_name.ilike(actor_search),
                    Users.last_name.ilike(actor_search),
                    Users.email.ilike(actor_search),
                    ActivityLog.description.ilike(actor_search),
                    ActivityLog.target_entity_name.ilike(actor_search),
                )
            )

        if start_date:
            query = query.where(ActivityLog.created_at >= normalize_to_utc(start_date))

        if end_date:
            query = query.where(ActivityLog.created_at < normalize_to_utc(end_date))
        elif date_range and not start_date:
            query = query.where(
                ActivityLog.created_at >= date_range.utc_start,
                ActivityLog.created_at < date_range.utc_end_exclusive,
            )

        total = await session.scalar(
            select(func.count()).select_from(query.subquery())
        )

        result = await session.execute(
            query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return result.all(), total or 0
