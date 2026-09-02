from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.interview import Interview
from app.model.employer_model.job import Job
from app.model.employer_model.job_posting_audit import JobPostingAudit


class EmployerProfileRepository:
    @staticmethod
    async def get_by_user_id(
        session: AsyncSession,
        user_id: UUID,
    ) -> Optional[EmployerProfile]:
        result = await session.execute(
            select(EmployerProfile).where(
                EmployerProfile.user_id == user_id,
                EmployerProfile.is_deleted == 0,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        profile: EmployerProfile,
    ) -> EmployerProfile:
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile

    @staticmethod
    async def save(
        session: AsyncSession,
        profile: EmployerProfile,
    ) -> EmployerProfile:
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile

    @staticmethod
    async def count_candidates_contacted(
        session: AsyncSession,
        employer_id: str,
    ) -> int:
        value = await session.scalar(
            select(func.count(func.distinct(JobApplication.candidate_id)))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
            )
        )
        return int(value or 0)

    @staticmethod
    async def count_interviews_scheduled(
        session: AsyncSession,
        employer_id: str,
    ) -> int:
        value = await session.scalar(
            select(func.count(Interview.interview_id))
            .join(JobApplication, JobApplication.application_id == Interview.application_id)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
            )
        )
        return int(value or 0)

    @staticmethod
    async def average_candidate_rating(
        session: AsyncSession,
        employer_id: str,
    ) -> float:
        value = await session.scalar(
            select(func.avg(JobApplication.candidate_rating))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
                JobApplication.candidate_rating.is_not(None),
            )
        )
        return round(float(value or 0), 1)

    @staticmethod
    async def count_responded_applications(
        session: AsyncSession,
        employer_id: str,
    ) -> tuple[int, int]:
        total = await session.scalar(
            select(func.count(JobApplication.application_id))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
            )
        )
        responded = await session.scalar(
            select(func.count(JobApplication.application_id))
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
                JobApplication.application_status.notin_(("APPLIED", "REVIEW")),
            )
        )
        return int(responded or 0), int(total or 0)

    @staticmethod
    async def fetch_active_jobs(
        session: AsyncSession,
        employer_id: str,
        limit: int = 10,
    ) -> list[Job]:
        result = await session.execute(
            select(Job)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                Job.status == "PUBLISHED",
            )
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def fetch_recent_activity(
        session: AsyncSession,
        employer_id: str,
        limit: int = 10,
    ):
        result = await session.execute(
            select(JobPostingAudit, Job)
            .outerjoin(Job, Job.job_id == JobPostingAudit.job_id)
            .where(JobPostingAudit.employer_id == employer_id)
            .order_by(JobPostingAudit.created_at.desc())
            .limit(limit)
        )
        return result.all()


class CompanyProfileRepository:
    @staticmethod
    async def get_by_employer_id(
        session: AsyncSession,
        employer_id: str,
    ) -> Optional[CompanyProfile]:
        result = await session.execute(
            select(CompanyProfile).where(CompanyProfile.employer_id == employer_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_public_id(
        session: AsyncSession,
        company_id: str,
    ) -> Optional[CompanyProfile]:
        result = await session.execute(
            select(CompanyProfile).where(CompanyProfile.company_id == company_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_public_by_id(
        session: AsyncSession,
        company_id: str,
    ) -> Optional[CompanyProfile]:
        result = await session.execute(
            select(CompanyProfile).where(
                CompanyProfile.company_id == company_id,
                CompanyProfile.is_public.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        profile: CompanyProfile,
    ) -> CompanyProfile:
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile

    @staticmethod
    async def save(
        session: AsyncSession,
        profile: CompanyProfile,
    ) -> CompanyProfile:
        session.add(profile)
        await session.flush()
        await session.refresh(profile)
        return profile

    @staticmethod
    def _search_conditions(
        name: Optional[str],
        industry: Optional[str],
        company_size: Optional[str],
        location: Optional[str],
        verification_status: Optional[str],
    ):
        conditions = [CompanyProfile.is_public.is_(True)]
        if name:
            conditions.append(CompanyProfile.company_name.ilike(f"%{name}%"))
        if industry:
            conditions.append(CompanyProfile.industry == industry)
        if company_size:
            conditions.append(CompanyProfile.company_size == company_size)
        if location:
            like_location = f"%{location}%"
            conditions.append(
                or_(
                    CompanyProfile.headquarters_country.ilike(like_location),
                    CompanyProfile.headquarters_state.ilike(like_location),
                    CompanyProfile.headquarters_city.ilike(like_location),
                    CompanyProfile.location.ilike(like_location),
                )
            )
        if verification_status:
            conditions.append(CompanyProfile.verification_status == verification_status)
        return and_(*conditions)

    @staticmethod
    async def search(
        session: AsyncSession,
        name: Optional[str],
        industry: Optional[str],
        company_size: Optional[str],
        location: Optional[str],
        verification_status: Optional[str],
        page: int,
        page_size: int,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[CompanyProfile], int]:
        conditions = CompanyProfileRepository._search_conditions(
            name,
            industry,
            company_size,
            location,
            verification_status,
        )
        total = await session.scalar(
            select(func.count(CompanyProfile.company_id)).where(conditions)
        )
        sort_columns = {
            "company_name": CompanyProfile.company_name,
            "industry": CompanyProfile.industry,
            "company_size": CompanyProfile.company_size,
            "created_at": CompanyProfile.created_at,
            "updated_at": CompanyProfile.updated_at,
        }
        sort_column = sort_columns.get(sort_by, CompanyProfile.company_name)
        order_clause = sort_column.desc() if sort_order.lower() == "desc" else sort_column.asc()
        result = await session.execute(
            select(CompanyProfile)
            .where(conditions)
            .order_by(order_clause)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)
