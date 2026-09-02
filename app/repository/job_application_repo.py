from __future__ import annotations

from datetime import datetime, time
from typing import List, Optional, Tuple
from uuid import UUID
from app.utils.utc import utc_now_naive

from sqlalchemy import func, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.model.candidate_model.application_note import ApplicationNote
from app.model.candidate_model.application_status_history import ApplicationStatusHistory
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume import CandidateResume
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.interview import Interview
from app.model.employer_model.job import Job
from app.model.authentication.users import Users


class JobApplicationRepo:
    OPEN_JOB_STATUSES = ("PUBLISHED",)

    @classmethod
    async def _get_candidate_id(cls, session: AsyncSession, user_id: UUID) -> Optional[str]:
        result = await session.execute(
            select(CandidateProfile.candidate_id).where(
                CandidateProfile.user_id == user_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_total_applications_for_job(cls, session: AsyncSession, job_id: str) -> int:
        result = await session.execute(
            select(func.count(JobApplication.application_id)).where(
                JobApplication.job_id == job_id,
                JobApplication.is_deleted.is_(False),
            )
        )
        return int(result.scalar_one() or 0)

    @classmethod
    async def get_applications_for_candidate(
        cls,
        session: AsyncSession,
        candidate_id: str,
        status: Optional[str] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
        date_from=None,
        date_to=None,
        sort_by: str = "APPLIED_DATE_DESC",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[int, List[JobApplication]]:
        base = (
            select(JobApplication)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .options(
                selectinload(JobApplication.job),
                selectinload(JobApplication.notes),
                selectinload(JobApplication.interviews),
            )
        )

        if status:
            base = base.where(JobApplication.application_status == status)
        if source:
            base = base.where(JobApplication.source == source)
        if search:
            search_term = f"%{search}%"
            base = base.join(Job, Job.job_id == JobApplication.job_id).where(
                (Job.title.ilike(search_term))
                | (Job.company_name.ilike(search_term))
                | (Job.location.ilike(search_term))
            )
        if date_from:
            base = base.where(JobApplication.applied_at >= datetime.combine(date_from, time.min))
        if date_to:
            base = base.where(JobApplication.applied_at <= datetime.combine(date_to, time.max))

        if sort_by == "APPLIED_DATE_ASC":
            order_by = JobApplication.applied_at.asc()
        elif sort_by == "JOB_TITLE_ASC":
            base = base.join(Job, Job.job_id == JobApplication.job_id) if not search else base
            order_by = Job.title.asc()
        elif sort_by == "JOB_TITLE_DESC":
            base = base.join(Job, Job.job_id == JobApplication.job_id) if not search else base
            order_by = Job.title.desc()
        elif sort_by == "STATUS_ASC":
            order_by = JobApplication.application_status.asc()
        elif sort_by == "STATUS_DESC":
            order_by = JobApplication.application_status.desc()
        else:
            order_by = JobApplication.applied_at.desc()

        count_q = select(func.count()).select_from(base.subquery())
        total = (await session.execute(count_q)).scalar_one()

        paged = (
            base.order_by(order_by)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await session.execute(paged)).scalars().all()
        return total, list(rows)

    @classmethod
    async def get_application_by_id(
        cls,
        session: AsyncSession,
        application_id: str,
        candidate_id: str,
    ) -> Optional[JobApplication]:
        result = await session.execute(
            select(JobApplication)
            .where(
                JobApplication.application_id == application_id,
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .options(
                selectinload(JobApplication.job),
                selectinload(JobApplication.status_history),
                selectinload(JobApplication.interviews),
                selectinload(JobApplication.notes),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_next_steps(cls, session: AsyncSession, candidate_id: str) -> List[JobApplication]:
        result = await session.execute(
            select(JobApplication)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
                JobApplication.next_step_text.isnot(None),
            )
            .options(selectinload(JobApplication.job))
            .order_by(JobApplication.next_step_due.asc().nulls_last())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_company_for_job(cls, session: AsyncSession, job: Job) -> Optional[CompanyProfile]:
        result = await session.execute(
            select(CompanyProfile).where(CompanyProfile.employer_id == job.employer_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_employer_user_id_for_job(cls, session: AsyncSession, job: Job) -> Optional[str]:
        """
        Resolves the recruiter/employer *user* account that owns a job
        posting, so notifications (e.g. a candidate nudge) can be routed
        to the right person. Job.employer_id points at
        EmployerProfile.id, whose user_id is the actual login account.
        """
        result = await session.execute(
            select(EmployerProfile.user_id).where(EmployerProfile.id == job.employer_id)
        )
        user_id = result.scalar_one_or_none()
        return str(user_id) if user_id is not None else None

    @classmethod
    async def get_candidate_display_name(cls, session: AsyncSession, candidate_id: str) -> str:
        """
        Resolves a candidate's display name (first + last name from the
        linked `users` row) for use in recruiter-facing notifications,
        e.g. "Jane Doe sent a nudge...". Falls back to a generic label
        if the candidate/user row can't be found, so notification
        creation never fails just because a name is missing.
        """
        result = await session.execute(
            select(Users.first_name, Users.last_name).join(
                CandidateProfile, CandidateProfile.user_id == Users.user_id
            ).where(CandidateProfile.candidate_id == candidate_id)
        )
        row = result.first()
        if not row:
            return "A candidate"
        name = " ".join(part for part in [row.first_name, row.last_name] if part)
        return name or "A candidate"

    @classmethod
    async def create_application(
        cls,
        session: AsyncSession,
        application: JobApplication,
        *,
        commit: bool = True,
    ) -> JobApplication:
        session.add(application)
        if commit:
            await session.commit()
        else:
            await session.flush()
        return application

    @classmethod
    async def job_exists(cls, session: AsyncSession, job_id: str) -> bool:
        result = await session.execute(
            select(func.count(Job.job_id)).where(
                Job.job_id == job_id,
                Job.is_deleted.is_(False),
            )
        )
        return (result.scalar_one() or 0) > 0

    @classmethod
    async def get_job_for_application(cls, session: AsyncSession, job_id: str) -> Optional[Job]:
        result = await session.execute(
            select(Job).where(
                Job.job_id == job_id,
                Job.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_job_with_skills(cls, session: AsyncSession, job_id: str) -> Optional[Job]:
        """Fetch a job (with its skills eager-loaded) regardless of whether
        it's currently open/published.

        Unlike `CandidateJobSearchRepo.get_job_details` (used for job
        search/browsing, which only returns jobs that are still accepting
        applications), this intentionally does not filter by `status`,
        `closed_at`, or `application_deadline` -- a candidate who already
        applied should still be able to pull up AI interview questions for
        that job while preparing, even if the job has since closed.
        """
        result = await session.execute(
            select(Job)
            .where(
                Job.job_id == job_id,
                Job.is_deleted.is_(False),
            )
            .options(selectinload(Job.skills))
        )
        return result.scalar_one_or_none()

    @classmethod
    async def resume_exists_for_candidate(
        cls,
        session: AsyncSession,
        candidate_id: str,
        resume_id: str,
    ) -> bool:
        result = await session.execute(
            select(func.count(CandidateResume.resume_id)).where(
                CandidateResume.resume_id == resume_id,
                CandidateResume.candidate_id == candidate_id,
                CandidateResume.is_deleted.is_(False),
            )
        )
        return (result.scalar_one() or 0) > 0

    @classmethod
    async def get_resume_for_candidate(
        cls,
        session: AsyncSession,
        candidate_id: str,
        resume_id: str,
    ) -> Optional[CandidateResume]:
        result = await session.execute(
            select(CandidateResume).where(
                CandidateResume.resume_id == resume_id,
                CandidateResume.candidate_id == candidate_id,
                CandidateResume.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def application_exists(cls, session: AsyncSession, candidate_id: str, job_id: str) -> bool:
        result = await session.execute(
            select(func.count(JobApplication.application_id)).where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.job_id == job_id,
                JobApplication.is_deleted.is_(False),
            )
        )
        return (result.scalar_one() or 0) > 0

    @classmethod
    async def update_status(
        cls,
        session: AsyncSession,
        application_id: str,
        candidate_id: str,
        new_status: str,
        changed_by: Optional[UUID] = None,
    ) -> Optional[JobApplication]:
        app = await cls.get_application_by_id(session, application_id, candidate_id)
        if not app:
            return None

        old_status = app.application_status

        await session.execute(
            sql_update(JobApplication)
            .where(JobApplication.application_id == application_id)
            .values(application_status=new_status, updated_at=utc_now_naive())
            .execution_options(synchronize_session="fetch")
        )

        history = ApplicationStatusHistory(
            application_id=application_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
        )
        session.add(history)
        await session.commit()

        return await cls.get_application_by_id(session, application_id, candidate_id)

    @classmethod
    async def upsert_next_step(
        cls,
        session: AsyncSession,
        application_id: str,
        candidate_id: str,
        next_step_text: str,
        next_step_due=None,
    ) -> bool:
        result = await session.execute(
            sql_update(JobApplication)
            .where(
                JobApplication.application_id == application_id,
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .values(
                next_step_text=next_step_text,
                next_step_due=next_step_due,
                updated_at=utc_now_naive(),
            )
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @classmethod
    async def set_interview_loop_date(
        cls,
        session: AsyncSession,
        application_id: str,
        candidate_id: str,
        interview_loop_date,
    ) -> bool:
        result = await session.execute(
            sql_update(JobApplication)
            .where(
                JobApplication.application_id == application_id,
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .values(interview_loop_date=interview_loop_date, updated_at=utc_now_naive())
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @classmethod
    async def withdraw_application(
        cls,
        session: AsyncSession,
        application_id: str,
        candidate_id: str,
        changed_by: Optional[UUID] = None,
    ) -> bool:
        app = await cls.get_application_by_id(session, application_id, candidate_id)
        if not app or app.application_status == "WITHDRAWN":
            return False

        result = await session.execute(
            sql_update(JobApplication)
            .where(
                JobApplication.application_id == application_id,
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
            )
            .values(
                application_status="WITHDRAWN",
                updated_at=utc_now_naive(),
            )
            .execution_options(synchronize_session="fetch")
        )

        history = ApplicationStatusHistory(
            application_id=application_id,
            old_status=app.application_status,
            new_status="WITHDRAWN",
            changed_by=changed_by,
        )
        session.add(history)
        await session.commit()
        return result.rowcount > 0

    @classmethod
    async def add_note(
        cls,
        session: AsyncSession,
        application_id: str,
        note_text: str,
        created_by: str,
    ) -> ApplicationNote:
        note = ApplicationNote(application_id=application_id, note_text=note_text, created_by=created_by)
        session.add(note)
        await session.commit()
        return note

    @classmethod
    async def get_notes(cls, session: AsyncSession, application_id: str) -> List[ApplicationNote]:
        result = await session.execute(
            select(ApplicationNote)
            .where(
                ApplicationNote.application_id == application_id,
                ApplicationNote.is_deleted.is_(False),
            )
            .order_by(ApplicationNote.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_note_by_id(
        cls,
        session: AsyncSession,
        note_id: str,
        application_id: str,
    ) -> Optional[ApplicationNote]:
        result = await session.execute(
            select(ApplicationNote).where(
                ApplicationNote.note_id == note_id,
                ApplicationNote.application_id == application_id,
                ApplicationNote.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def update_note(
        cls,
        session: AsyncSession,
        note_id: str,
        application_id: str,
        note_text: str,
    ) -> bool:
        result = await session.execute(
            sql_update(ApplicationNote)
            .where(
                ApplicationNote.note_id == note_id,
                ApplicationNote.application_id == application_id,
                ApplicationNote.is_deleted.is_(False),
            )
            .values(note_text=note_text, updated_at=utc_now_naive())
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0

    @classmethod
    async def delete_note(cls, session: AsyncSession, note_id: str, application_id: str) -> bool:
        result = await session.execute(
            sql_update(ApplicationNote)
            .where(
                ApplicationNote.note_id == note_id,
                ApplicationNote.application_id == application_id,
                ApplicationNote.is_deleted.is_(False),
            )
            .values(is_deleted=True, deleted_at=utc_now_naive())
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        return result.rowcount > 0