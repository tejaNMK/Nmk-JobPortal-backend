from datetime import date, datetime
from typing import List, Optional, Tuple
from uuid import UUID
from app.utils.utc import utc_now_naive

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.authentication.users import Users
from app.model.candidate_model.application_status_history import ApplicationStatusHistory
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume import CandidateResume
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job


class ShortlistedCandidatesRepo:

    @classmethod
    async def get_application_for_employer(
        cls,
        session: AsyncSession,
        employer_id: str,
        application_id: str,
    ) -> Optional[JobApplication]:
        """Return the JobApplication only if it belongs to a job owned by the employer."""

        result = await session.execute(
            select(JobApplication)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                JobApplication.application_id == application_id,
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def update_application_shortlist_status(
        cls,
        session: AsyncSession,
        application_id: str,
        status: str,
        clear_shortlisted_at: bool = False,
        changed_by: UUID | None = None,
        previous_status: str | None = None,
        reason: str | None = None,
    ) -> Optional[JobApplication]:
        application_result = await session.execute(
            select(JobApplication).where(
                JobApplication.application_id == application_id,
                JobApplication.is_deleted.is_(False),
            )
        )
        application = application_result.scalar_one_or_none()

        if not application:
            return None

        old_status = previous_status if previous_status is not None else application.application_status
        application.application_status = status
        application.updated_at = utc_now_naive()

        if clear_shortlisted_at:
            application.shortlisted_at = None
        elif status.upper() == "SHORTLISTED" and not application.shortlisted_at:
            application.shortlisted_at = utc_now_naive()

        session.add(application)
        if changed_by is not None and (old_status or "").upper() != status.upper():
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
    async def get_shortlisted_candidates(
        cls,
        session: AsyncSession,
        employer_id: str,
        search: Optional[str],
        status: Optional[str],
        job_role: Optional[str],
        date_from: Optional[date],
        date_to: Optional[date],
        page: int,
        page_size: int,
        sort_by: Optional[str] = None,
        statuses: Optional[List[str]] = None,
    ) -> Tuple[int, List]:
        status_values = statuses or [
            "SHORTLISTED",
            "INTERVIEW_SCHEDULED",
            "ON_HOLD",
            "HIRED",
        ]

        query = (
            select(
                JobApplication,
                CandidateProfile,
                Users,
                CandidateResume,
                Job
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
                CandidateResume.resume_id == JobApplication.resume_id
            )
            .where(
                Job.employer_id == employer_id,
                JobApplication.is_deleted.is_(False),
                JobApplication.application_status.in_(status_values)
            )
        )

        if search:
            query = query.where(
                or_(
                    Users.first_name.ilike(f"%{search}%"),
                    Users.last_name.ilike(f"%{search}%"),
                    Users.email.ilike(f"%{search}%"),
                    Job.title.ilike(f"%{search}%")
                )
            )

        if status:
            query = query.where(
                JobApplication.application_status == status
            )

        if job_role:
            query = query.where(
                Job.title.ilike(
                    f"%{job_role}%"
                )
            )

        if date_from:
            query = query.where(
                func.date(
                    JobApplication.shortlisted_at
                ) >= date_from
            )

        if date_to:
            query = query.where(
                func.date(
                    JobApplication.shortlisted_at
                ) <= date_to
            )

        count_query = (
            select(func.count())
            .select_from(query.subquery())
        )

        total = (
            await session.execute(count_query)
        ).scalar_one()

        if sort_by == "NAME_ASC":
            query = query.order_by(
                Users.first_name.asc()
            )

        elif sort_by == "NAME_DESC":
            query = query.order_by(
                Users.first_name.desc()
            )

        elif sort_by == "RATING_HIGH":
            query = query.order_by(
                JobApplication.candidate_rating.desc()
            )

        elif sort_by == "RATING_LOW":
            query = query.order_by(
                JobApplication.candidate_rating.asc()
            )

        elif sort_by == "ROLE_ASC":
            query = query.order_by(
                Job.title.asc()
            )

        elif sort_by == "ROLE_DESC":
            query = query.order_by(
                Job.title.desc()
            )

        elif sort_by == "DATE_OLDEST":
            query = query.order_by(
                JobApplication.shortlisted_at.asc()
            )

        else:
            query = query.order_by(
                JobApplication.shortlisted_at.desc()
            )

        query = (
            query.offset((page - 1) * page_size)
            .limit(page_size)
        )

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

        result = await session.execute(
            select(
                JobApplication,
                CandidateProfile,
                Users,
                CandidateResume,
                Job
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
                CandidateResume.resume_id == JobApplication.resume_id
            )
            .where(
                JobApplication.application_id == application_id,
                Job.employer_id == employer_id
            )
        )

        return result.first()
    
    @classmethod
    async def get_application_by_id(
        cls,
        session: AsyncSession,
        application_id: str,
    ):

        result = await session.execute(
            select(JobApplication).where(
                JobApplication.application_id == application_id
            )
        )

        return result.scalar_one_or_none()

    @classmethod
    async def update_rating(
        cls,
        session: AsyncSession,
        application_id: str,
        rating: int
    ):

        result = await session.execute(
            select(JobApplication).where(
                JobApplication.application_id == application_id
            )
        )

        application = result.scalar_one_or_none()

        if not application:
            return None

        application.candidate_rating = rating

        session.add(application)
        await session.commit()
        await session.refresh(application)

        return application

    @classmethod
    async def update_status(
        cls,
        session: AsyncSession,
        application_id: str,
        status: str,
        changed_by: UUID | None = None,
        previous_status: str | None = None,
        reason: str | None = None,
        commit: bool = True,
    ):

        result = await session.execute(
            select(JobApplication).where(
                JobApplication.application_id == application_id
            )
        )

        application = result.scalar_one_or_none()

        if not application:
            return None

        old_status = previous_status if previous_status is not None else application.application_status
        application.application_status = status
        application.updated_at = utc_now_naive()

        if (
            status == "SHORTLISTED"
            and not application.shortlisted_at
        ):
            application.shortlisted_at = utc_now_naive()

        session.add(application)
        if changed_by is not None and (old_status or "").upper() != status.upper():
            session.add(
                ApplicationStatusHistory(
                    application_id=application.application_id,
                    old_status=old_status,
                    new_status=status,
                    changed_by=changed_by,
                    reason=reason,
                )
            )
        if commit:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(application)

        return application
    
    
    @classmethod
    async def get_applications_by_ids(
        cls,
        session: AsyncSession,
        application_ids: List[str],
        employer_id: str | None = None,
    ):

        query = select(JobApplication).where(
            JobApplication.application_id.in_(
                application_ids
            ),
            JobApplication.is_deleted.is_(False),
        )
        if employer_id is not None:
            query = query.join(Job, Job.job_id == JobApplication.job_id).where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
            )

        result = await session.execute(query)

        return result.scalars().all()
    
    @classmethod
    async def get_notes(
        cls,
        session: AsyncSession,
        application_id: str,
    ):

        return await cls.get_application_by_id(
            session=session,
            application_id=application_id,
        )
    
    @classmethod
    async def update_notes(
        cls,
        session: AsyncSession,
        application_id: str,
        remarks: str,
    ):

        application = await cls.get_application_by_id(
            session=session,
            application_id=application_id,
        )

        if not application:
            return None

        application.recruiter_notes = remarks

        session.add(application)

        await session.commit()

        await session.refresh(application)

        return application
    
    @classmethod
    async def get_interview_email_details(
        cls,
        session: AsyncSession,
        application_id: str,
    ):

        result = await session.execute(
            select(
                Users.first_name,
                Users.last_name,
                Users.email,
                Users.user_id,
                CandidateProfile.candidate_id,
                EmployerProfile.company_name,
                EmployerProfile.company_email,
                EmployerProfile.user_id,
                Job.title,
                JobApplication.resume_id,
            )
            .select_from(JobApplication)
            .join(
                CandidateProfile,
                CandidateProfile.candidate_id == JobApplication.candidate_id,
            )
            .join(
                Users,
                Users.user_id == CandidateProfile.user_id,
            )
            .join(
                Job,
                Job.job_id == JobApplication.job_id,
            )
            .join(
                EmployerProfile,
                EmployerProfile.id == Job.employer_id,
            )
            .where(
                JobApplication.application_id == application_id,
            )
        )

        return result.first()

    @classmethod
    async def get_candidate_resume_for_interview(
        cls,
        session: AsyncSession,
        application_id: str,
    ):
        result = await session.execute(
            select(CandidateResume)
            .select_from(JobApplication)
            .join(
                CandidateResume,
                CandidateResume.resume_id == JobApplication.resume_id,
            )
            .where(
                JobApplication.application_id == application_id,
                JobApplication.resume_id.is_not(None),
                CandidateResume.candidate_id == JobApplication.candidate_id,
                CandidateResume.is_deleted.is_(False),
            )
            .limit(1)
        )

        return result.scalar_one_or_none()
