from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.config import commit_rollback
from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_saved_job import CandidateSavedJob
from app.model.candidate_model.job_alert import JobAlert
from app.model.candidate_model.job_application import JobApplication
from app.model.candidate_model.candidate_resume import CandidateResume
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.subscription.subscription import Subscription
from app.model.subscription.user_subscription import UserSubscription
from app.utils.date_range import normalize_datetime_for_db


class CandidateRepository:

    @staticmethod
    async def list_candidates(
        session: AsyncSession,
        page: int,
        page_size: int,
        search: str | None = None,
        status: Optional[str] = None,
        subscription: Optional[str] = None,
        registered_from: Optional[datetime] = None,
        registered_to: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ):
        resume_count = (
            select(
                CandidateResume.candidate_id,
                func.count(CandidateResume.resume_id).label("resume_count"),
            )
            .where(CandidateResume.is_deleted.is_(False))
            .group_by(CandidateResume.candidate_id)
            .subquery()
        )

        query = (
            select(
                CandidateProfile,
                Users,
                Subscription.subscription_name,
                func.coalesce(resume_count.c.resume_count, 0).label("resume_count"),
            )
            .join(
                Users,
                Users.user_id == CandidateProfile.user_id,
            )
            .outerjoin(
                UserSubscription,
                (UserSubscription.user_id == Users.user_id)
                & (UserSubscription.status == "ACTIVE"),
            )
            .outerjoin(
                Subscription,
                Subscription.subscription_id == UserSubscription.subscription_id,
            )
            .outerjoin(
                resume_count,
                resume_count.c.candidate_id == CandidateProfile.candidate_id,
            )
            .options(selectinload(Users.roles))
            .where(
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )

        if search:

            query = query.where(
                or_(
                    Users.first_name.ilike(f"%{search}%"),
                    Users.last_name.ilike(f"%{search}%"),
                    Users.email.ilike(f"%{search}%"),
                    Users.mobile_number.ilike(f"%{search}%"),
                    CandidateProfile.headline.ilike(f"%{search}%"),
                )
            )

        if status:
            query = query.where(CandidateProfile.status == status.upper())

        if subscription:
            query = query.where(
                Subscription.subscription_name.ilike(f"%{subscription}%")
            )

        if registered_from:
            query = query.where(Users.created_at >= normalize_datetime_for_db(registered_from))

        if registered_to:
            query = query.where(Users.created_at <= normalize_datetime_for_db(registered_to))

        total = await session.scalar(
            select(func.count())
            .select_from(query.subquery())
        )

        sort_key = (sort_by or "created_at").lower()
        sort_direction = (sort_order or "desc").lower()
        if sort_key == "oldest":
            sort_key = "created_at"
            sort_direction = "asc"
        elif sort_key == "newest":
            sort_key = "created_at"
            sort_direction = "desc"

        sort_columns = {
            "created_at": Users.created_at,
            "registered_on": Users.created_at,
            "name": Users.first_name,
        }
        sort_column = sort_columns.get(sort_key, Users.created_at)
        order_by = sort_column.asc() if sort_direction == "asc" else sort_column.desc()

        result = await session.execute(
            query.order_by(order_by)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return result.all(), total or 0
    
    @staticmethod
    async def get_candidate(
        session: AsyncSession,
        candidate_id: str,
    ):

        result = await session.execute(
            select(CandidateProfile, Users)
            .join(
                Users,
                Users.user_id == CandidateProfile.user_id,
            )
            .options(selectinload(Users.roles))
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )

        return result.first()

    @staticmethod
    async def get_latest_resume_detail(
        session: AsyncSession,
        candidate_id: str,
    ):
        result = await session.execute(
            select(CandidateResumeDetail)
            .where(
                CandidateResumeDetail.candidate_id == candidate_id,
                CandidateResumeDetail.is_deleted.is_(False),
            )
            .order_by(CandidateResumeDetail.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_resumes(
        session: AsyncSession,
        candidate_id: str,
    ):
        result = await session.execute(
            select(CandidateResume)
            .where(
                CandidateResume.candidate_id == candidate_id,
                CandidateResume.is_deleted.is_(False),
            )
            .order_by(CandidateResume.uploaded_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_active_subscription(
        session: AsyncSession,
        user_id,
    ):
        result = await session.execute(
            select(UserSubscription, Subscription)
            .join(
                Subscription,
                Subscription.subscription_id == UserSubscription.subscription_id,
            )
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status == "ACTIVE",
            )
            .order_by(UserSubscription.created_at.desc())
            .limit(1)
        )
        return result.first()

    @staticmethod
    async def get_candidate_statistics(
        session: AsyncSession,
        candidate_id: str,
    ):

        applications = await session.scalar(
            select(func.count(JobApplication.application_id))
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
        )

        saved_jobs = await session.scalar(
            select(func.count(CandidateSavedJob.saved_job_id))
            .where(
                CandidateSavedJob.candidate_id == candidate_id,
                CandidateSavedJob.deleted_at.is_(None),
            )
        )

        job_alerts = await session.scalar(
            select(func.count(JobAlert.alert_id))
            .where(
                JobAlert.candidate_id == candidate_id,
            )
        )

        resumes = await session.scalar(
            select(func.count(CandidateResume.resume_id))
            .where(
                CandidateResume.candidate_id == candidate_id,
                CandidateResume.is_deleted.is_(False),
            )
        )

        return {
            "applications": applications or 0,
            "saved_jobs": saved_jobs or 0,
            "job_alerts": job_alerts or 0,
            "resumes": resumes or 0,
        }
    
    @staticmethod
    async def update_candidate_status(
        session: AsyncSession,
        candidate_id: str,
        status: str,
        reason: Optional[str] = None,
    ):

        result = await session.execute(
            select(CandidateProfile)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )

        candidate = result.scalar_one_or_none()

        if not candidate:
            return None

        candidate.status = status
        candidate.suspension_reason = reason if status == "SUSPENDED" else None

        await commit_rollback(session)

        return candidate


    @staticmethod
    async def update_user_status(
        session: AsyncSession,
        user_id,
        status: str,
    ):

        result = await session.execute(
            select(Users)
            .where(
                Users.user_id == user_id,
                Users.deleted_flag.is_(False),
            )
        )

        user = result.scalar_one_or_none()

        if not user:
            return None

        user.user_status = status

        await commit_rollback(session)

        return user

    @staticmethod
    async def update_candidate(
        session: AsyncSession,
        candidate_id: str,
        user_updates: dict,
        profile_updates: dict,
    ):
        result = await session.execute(
            select(CandidateProfile, Users)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )
        row = result.first()
        if not row:
            return None

        profile, user = row
        for key, value in user_updates.items():
            setattr(user, key, value)
        for key, value in profile_updates.items():
            setattr(profile, key, value)
        profile.updated_at = utc_now_naive()

        await commit_rollback(session)
        return profile, user

    @staticmethod
    async def soft_delete_candidate(
        session: AsyncSession,
        candidate_id: str,
        deleted_by: Optional[str] = None,
    ):
        result = await session.execute(
            select(CandidateProfile, Users)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
        )
        row = result.first()
        if not row:
            return None

        profile, user = row
        now = utc_now_naive()
        profile.is_deleted = True
        profile.deleted_at = now
        profile.deleted_by = deleted_by
        user.deleted_flag = True
        user.deleted_at = now

        await commit_rollback(session)
        return profile, user
