from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID
from app.utils.utc import utc_now_naive

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.model.authentication.users import Users
from app.model.candidate_model.application_status_history import ApplicationStatusHistory
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume import CandidateResume
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.candidate_recommendation import CandidateRecommendation
from app.model.employer_model.job import Job


class JobApplicantsRepo:
    @staticmethod
    def _latest_resume_detail_subquery():
        return (
            select(
                CandidateResumeDetail.candidate_id.label("candidate_id"),
                func.max(CandidateResumeDetail.generated_at).label("generated_at"),
            )
            .where(CandidateResumeDetail.is_deleted.is_(False))
            .group_by(CandidateResumeDetail.candidate_id)
            .subquery()
        )

    @classmethod
    async def get_employer_id(
        cls,
        session: AsyncSession,
        user_id: UUID
    ) -> Optional[str]:

        result = await session.execute(
            select(EmployerProfile.id).where(
                EmployerProfile.user_id == user_id
            )
        )

        return result.scalar_one_or_none()

    @classmethod
    async def get_job_applicants(
        cls,
        session: AsyncSession,
        employer_id: str,
        job_id: Optional[str],
        search: Optional[str],
        status: Optional[str],
        sort_by: Optional[str],
        sort_order: str,
        page: int,
        page_size: int,
        ranking_limit: Optional[int] = None,
    ) -> Tuple[int, List]:

        latest_resume_detail = cls._latest_resume_detail_subquery()
        query = (
            select(
                JobApplication,
                CandidateProfile,
                Users,
                CandidateResume,
                Job,
                CandidateResumeDetail,
            )
            .join(
                Job,
                Job.job_id == JobApplication.job_id
            )
            .join(
                CandidateProfile,
                CandidateProfile.candidate_id == JobApplication.candidate_id
            )
            .join(
                Users,
                Users.user_id == CandidateProfile.user_id
            )
            .outerjoin(
                CandidateResume,
                and_(
                    CandidateResume.resume_id == JobApplication.resume_id,
                    CandidateResume.is_deleted.is_(False),
                )
            )
            .outerjoin(
                latest_resume_detail,
                latest_resume_detail.c.candidate_id == CandidateProfile.candidate_id,
            )
            .outerjoin(
                CandidateResumeDetail,
                and_(
                    CandidateResumeDetail.candidate_id == CandidateProfile.candidate_id,
                    CandidateResumeDetail.generated_at == latest_resume_detail.c.generated_at,
                    CandidateResumeDetail.is_deleted.is_(False),
                ),
            )
            .where(
                Job.employer_id == employer_id,
                JobApplication.is_deleted.is_(False),
                Job.is_deleted.is_(False),
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
        )

        if job_id:
            query = query.where(Job.job_id == job_id)

        if search:
            term = f"%{search}%"
            query = query.where(
                or_(
                    Users.first_name.ilike(term),
                    Users.last_name.ilike(term),
                    Users.email.ilike(term),
                    CandidateProfile.headline.ilike(term),
                    CandidateProfile.current_company.ilike(term),
                    CandidateProfile.skills_summary.ilike(term),
                    Job.title.ilike(term),
                )
            )

        if status:
            query = query.where(
                JobApplication.application_status == status.upper()
            )

        count_query = select(
            func.count()
        ).select_from(
            query.subquery()
        )

        total = (
            await session.execute(count_query)
        ).scalar_one()

        sort_columns = {
            "applied_at": JobApplication.applied_at,
            "application_date": JobApplication.applied_at,
            "status": JobApplication.application_status,
            "name": Users.first_name,
            "candidate_name": Users.first_name,
            "experience": CandidateProfile.total_experience,
            "job_title": Job.title,
        }
        sort_column = sort_columns.get((sort_by or "applied_at").lower(), JobApplication.applied_at)
        order = sort_column.asc() if (sort_order or "").lower() == "asc" else sort_column.desc()

        query = query.order_by(order, JobApplication.application_id.asc()).options(
            selectinload(Job.skills)
        )
        if (sort_by or "").lower() in {"best_match", "match_score"}:
            if ranking_limit:
                query = query.limit(ranking_limit)
        else:
            query = query.offset((page - 1) * page_size).limit(page_size)

        rows = (
            await session.execute(query)
        ).all()

        return total, rows

    @classmethod
    async def get_application_details(
        cls,
        session: AsyncSession,
        employer_id: str,
        application_id: str
    ):

        latest_resume_detail = cls._latest_resume_detail_subquery()
        result = await session.execute(
            select(
                JobApplication,
                CandidateProfile,
                Users,
                CandidateResume,
                Job,
                CandidateResumeDetail,
            )
            .join(
                Job,
                Job.job_id == JobApplication.job_id
            )
            .join(
                CandidateProfile,
                CandidateProfile.candidate_id == JobApplication.candidate_id
            )
            .join(
                Users,
                Users.user_id == CandidateProfile.user_id
            )
            .outerjoin(
                CandidateResume,
                and_(
                    CandidateResume.resume_id == JobApplication.resume_id,
                    CandidateResume.is_deleted.is_(False),
                )
            )
            .outerjoin(
                latest_resume_detail,
                latest_resume_detail.c.candidate_id == CandidateProfile.candidate_id,
            )
            .outerjoin(
                CandidateResumeDetail,
                and_(
                    CandidateResumeDetail.candidate_id == CandidateProfile.candidate_id,
                    CandidateResumeDetail.generated_at == latest_resume_detail.c.generated_at,
                    CandidateResumeDetail.is_deleted.is_(False),
                ),
            )
            .where(
                JobApplication.application_id == application_id,
                Job.employer_id == employer_id,
                JobApplication.is_deleted.is_(False),
                Job.is_deleted.is_(False),
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
            .options(selectinload(Job.skills))
        )

        return result.first()

    @classmethod
    async def get_cached_candidate_recommendation(
        cls,
        session: AsyncSession,
        *,
        job_id: str,
        candidate_id: str,
        application_id: str,
    ) -> Optional[CandidateRecommendation]:
        result = await session.execute(
            select(CandidateRecommendation)
            .where(
                CandidateRecommendation.job_id == job_id,
                CandidateRecommendation.candidate_id == candidate_id,
                or_(
                    CandidateRecommendation.application_id == application_id,
                    CandidateRecommendation.application_id.is_(None),
                ),
            )
            .order_by(CandidateRecommendation.application_id.desc().nullslast())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def save_candidate_recommendation(
        cls,
        session: AsyncSession,
        recommendation: CandidateRecommendation,
    ) -> CandidateRecommendation:
        session.add(recommendation)
        await session.commit()
        await session.refresh(recommendation)
        return recommendation

    @classmethod
    async def get_employer_application(
        cls,
        session: AsyncSession,
        employer_id: str,
        application_id: str,
    ) -> Optional[JobApplication]:

        result = await session.execute(
            select(JobApplication)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                JobApplication.application_id == application_id,
                Job.employer_id == employer_id,
                JobApplication.is_deleted.is_(False),
                Job.is_deleted.is_(False),
            )
            .with_for_update()
        )

        return result.scalar_one_or_none()

    @classmethod
    async def get_application_by_id(
        cls,
        session: AsyncSession,
        application_id: str,
    ) -> Optional[JobApplication]:

        result = await session.execute(
            select(JobApplication)
            .where(
                JobApplication.application_id == application_id,
                JobApplication.is_deleted.is_(False),
            )
            .with_for_update()
        )

        return result.scalar_one_or_none()

    @classmethod
    async def update_application_status(
        cls,
        session: AsyncSession,
        application: JobApplication,
        status: str,
        changed_by: UUID,
        reason: Optional[str] = None,
    ) -> JobApplication:

        old_status = application.application_status
        now = utc_now_naive()

        application.application_status = status
        application.updated_at = now
        if status == "SHORTLISTED" and not application.shortlisted_at:
            application.shortlisted_at = now
        if reason:
            application.recruiter_notes = reason

        session.add(application)
        session.add(
            ApplicationStatusHistory(
                application_id=application.application_id,
                old_status=old_status,
                new_status=status,
                changed_by=changed_by,
                reason=reason,
            )
        )

        await session.commit()
        await session.refresh(application)

        return application
