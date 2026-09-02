
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.authentication.users import Users
from app.model.candidate_model.candidate_company_following import CandidateCompanyFollowing
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume import CandidateResume
from app.model.candidate_model.job_application import JobApplication
from app.model.candidate_model.job_recommendation import JobRecommendation
from app.model.candidate_model.message import Message
from app.model.candidate_model.profile_view_event import ProfileViewEvent
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.job import Job


class DashboardRepo:

    @classmethod
    async def fetch_profile_and_user(cls, session: AsyncSession, user_id: UUID) -> Tuple[Optional[CandidateProfile], Optional[Users]]:
        profile_result = await session.execute(
            select(CandidateProfile).where(
                CandidateProfile.user_id == user_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )
        profile = profile_result.scalar_one_or_none()

        user_result = await session.execute(
            select(Users).where(Users.user_id == user_id)
        )
        user = user_result.scalar_one_or_none()

        return profile, user

    @classmethod
    async def fetch_cv_count(cls, session: AsyncSession, candidate_id: str) -> int:
        result = await session.execute(
            select(func.count(CandidateResume.resume_id)).where(
                CandidateResume.candidate_id == candidate_id,
                CandidateResume.is_deleted.is_(False),
            )
        )
        return result.scalar_one() or 0

    @classmethod
    async def fetch_unread_message_count(cls, session: AsyncSession, user_id: UUID) -> int:
        result = await session.execute(
            select(func.count(Message.message_id)).where(
                Message.receiver_id == user_id,
                Message.read_flag.is_(False),
                Message.is_deleted.is_(False),
            )
        )
        return result.scalar_one() or 0

    @classmethod
    async def fetch_profile_views_count(cls, session: AsyncSession, candidate_id: str) -> int:
        result = await session.execute(
            select(func.count(ProfileViewEvent.view_id)).where(
                ProfileViewEvent.candidate_id == candidate_id,
            )
        )
        return result.scalar_one() or 0

    @classmethod
    async def fetch_followings_count(cls, session: AsyncSession, candidate_id: str) -> int:
        result = await session.execute(
            select(func.count(CandidateCompanyFollowing.following_id)).where(
                CandidateCompanyFollowing.candidate_id == candidate_id,
                CandidateCompanyFollowing.is_deleted.is_(False),
            )
        )
        return result.scalar_one() or 0

    @classmethod
    async def fetch_application_stats(cls, session: AsyncSession, candidate_id: str) -> List[Tuple[str, int]]:
        rows = await session.execute(
            select(
                JobApplication.application_status,
                func.count(JobApplication.application_id).label("cnt"),
            )
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .group_by(JobApplication.application_status)
        )
        return [(row.application_status, row.cnt) for row in rows.all()]

    @classmethod
    async def fetch_recent_applications(cls, session: AsyncSession, candidate_id: str, limit: int = 5) -> List[JobApplication]:
        result = await session.execute(
            select(JobApplication)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .options(selectinload(JobApplication.job))
            .order_by(JobApplication.applied_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @classmethod
    async def fetch_recommendations(cls, session: AsyncSession, candidate_id: str, limit: int = 5) -> List[JobRecommendation]:
        result = await session.execute(
            select(JobRecommendation)
            .where(JobRecommendation.candidate_id == candidate_id)
            .options(selectinload(JobRecommendation.job))
            .order_by(JobRecommendation.match_score.desc().nulls_last())
            .limit(limit)
        )
        return list(result.scalars().all())

    @classmethod
    async def fetch_companies_by_employer_ids(cls, session: AsyncSession, employer_ids: List[str]) -> Dict[str, CompanyProfile]:
        if not employer_ids:
            return {}
        result = await session.execute(
            select(CompanyProfile).where(
                CompanyProfile.employer_id.in_(employer_ids)
            )
        )
        return {cp.employer_id: cp for cp in result.scalars().all()}

    @classmethod
    async def fetch_followings(cls, session: AsyncSession, candidate_id: str, limit: int = 10) -> List[CandidateCompanyFollowing]:
        result = await session.execute(
            select(CandidateCompanyFollowing)
            .where(
                CandidateCompanyFollowing.candidate_id == candidate_id,
                CandidateCompanyFollowing.is_deleted.is_(False),
            )
            .options(selectinload(CandidateCompanyFollowing.company))
            .order_by(CandidateCompanyFollowing.followed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @classmethod
    async def fetch_open_jobs_count_by_company(cls, session: AsyncSession, company_ids: List[str]) -> Dict[str, int]:
        if not company_ids:
            return {}
        rows = await session.execute(
            select(
                CompanyProfile.company_id,
                func.count(Job.job_id).label("cnt"),
            )
            .join(Job, Job.employer_id == CompanyProfile.employer_id)
            .where(
                CompanyProfile.company_id.in_(company_ids),
                Job.status == "PUBLISHED",
                Job.closed_at.is_(None),
                Job.is_deleted.is_(False),
            )
            .group_by(CompanyProfile.company_id)
        )
        return {row.company_id: row.cnt for row in rows.all()}
