from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional, Tuple
from app.utils.utc import utc_now_naive

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.candidate_invitation import CandidateInvitation
from app.model.employer_model.job import Job
from app.model.employer_model.job_skill import JobSkill
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.company_profile import CompanyProfile
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.authentication.users import Users
from app.model.candidate_model.job_application import JobApplication


class InvitationsRepository:
    INVITATION_ACTIVE_STATUSES = ("PENDING", "VIEWED")

    @staticmethod
    async def create_invitation(
        session: AsyncSession,
        *,
        invitation: CandidateInvitation,
    ) -> CandidateInvitation:
        session.add(invitation)
        await session.commit()
        await session.refresh(invitation)
        return invitation

    @staticmethod
    async def has_duplicate_active_invitation(
        session: AsyncSession,
        *,
        employer_id: str,
        candidate_id: str,
        job_id: str,
    ) -> bool:
        q = (
            select(func.count(CandidateInvitation.invitation_id))
            .where(
                CandidateInvitation.employer_id == employer_id,
                CandidateInvitation.candidate_id == candidate_id,
                CandidateInvitation.job_id == job_id,
                CandidateInvitation.status.in_(InvitationsRepository.INVITATION_ACTIVE_STATUSES),
            )
        )
        value = await session.scalar(q)
        return (value or 0) > 0

    @staticmethod
    async def get_job_owned_by_employer(
        session: AsyncSession,
        *,
        employer_id: str,
        job_id: str,
    ) -> Optional[Job]:
        q = select(Job).where(
            Job.job_id == job_id,
            Job.employer_id == employer_id,
            Job.is_deleted.is_(False),
        )
        return (await session.execute(q)).scalar_one_or_none()

    @staticmethod
    async def get_invitation_by_id_and_candidate(
        session: AsyncSession,
        *,
        invitation_id: str,
        candidate_id: str,
    ) -> Optional[CandidateInvitation]:
        q = select(CandidateInvitation).where(
            CandidateInvitation.invitation_id == invitation_id,
            CandidateInvitation.candidate_id == candidate_id,
        )
        return (await session.execute(q)).scalar_one_or_none()

    @staticmethod
    async def update_invitation_status(
        session: AsyncSession,
        *,
        invitation: CandidateInvitation,
        new_status: str,
        responded_at: Optional[datetime] = None,
        accepted_at: Optional[datetime] = None,
        rejected_at: Optional[datetime] = None,
        viewed_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> CandidateInvitation:
        invitation.status = new_status
        if responded_at is not None:
            invitation.responded_at = responded_at
        if accepted_at is not None:
            invitation.accepted_at = accepted_at
        if rejected_at is not None:
            invitation.rejected_at = rejected_at
        if viewed_at is not None:
            invitation.viewed_at = viewed_at
        if updated_at is not None:
            invitation.updated_at = updated_at
        await session.commit()
        await session.refresh(invitation)
        return invitation

    @staticmethod
    async def list_employer_invitations(
        session: AsyncSession,
        *,
        employer_id: str,
        filters,
    ) -> Tuple[int, List[Tuple[CandidateInvitation, CandidateProfile, Users, Job]]]:
        base = (
            select(CandidateInvitation, CandidateProfile, Users, Job)
            .join(CandidateProfile, CandidateProfile.candidate_id == CandidateInvitation.candidate_id)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .join(Job, Job.job_id == CandidateInvitation.job_id)
            .where(CandidateInvitation.employer_id == employer_id)
        )

        if filters.job_id:
            base = base.where(CandidateInvitation.job_id == filters.job_id)
        if filters.candidate_id:
            base = base.where(CandidateInvitation.candidate_id == filters.candidate_id)
        if filters.status:
            base = base.where(CandidateInvitation.status == filters.status)
        if filters.date_from:
            start_dt = datetime.combine(filters.date_from, datetime.min.time())
            base = base.where(CandidateInvitation.invited_at >= start_dt)
        if filters.date_to:
            end_dt = datetime.combine(filters.date_to, datetime.max.time())
            base = base.where(CandidateInvitation.invited_at <= end_dt)

        sort_col = CandidateInvitation.created_at.desc() if filters.sort_by != "oldest" else CandidateInvitation.created_at.asc()
        count_q = select(func.count()).select_from(base.subquery())
        total = await session.scalar(count_q)

        rows_q = (
            base.order_by(sort_col)
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        rows = list((await session.execute(rows_q)).all())
        return int(total or 0), rows

    @staticmethod
    async def list_candidate_invitations(
        session: AsyncSession,
        *,
        candidate_id: str,
        filters,
    ) -> Tuple[int, List[Tuple[CandidateInvitation, Job, EmployerProfile, Users, Optional[CompanyProfile]]]]:
        base = (
            select(CandidateInvitation, Job, EmployerProfile, Users, CompanyProfile)
            .join(Job, Job.job_id == CandidateInvitation.job_id)
            .join(EmployerProfile, EmployerProfile.id == CandidateInvitation.employer_id)
            .join(Users, Users.user_id == EmployerProfile.user_id)
            .outerjoin(CompanyProfile, CompanyProfile.employer_id == EmployerProfile.id)
            .where(CandidateInvitation.candidate_id == candidate_id)
        )

        if filters.status:
            base = base.where(CandidateInvitation.status == str(filters.status).upper())
        if filters.date_from:
            start_dt = datetime.combine(filters.date_from, datetime.min.time())
            base = base.where(CandidateInvitation.invited_at >= start_dt)
        if filters.date_to:
            end_dt = datetime.combine(filters.date_to, datetime.max.time())
            base = base.where(CandidateInvitation.invited_at <= end_dt)

        sort_col = CandidateInvitation.created_at.desc() if filters.sort_by != "oldest" else CandidateInvitation.created_at.asc()
        count_q = select(func.count()).select_from(base.subquery())
        total = await session.scalar(count_q)

        rows_q = (
            base.order_by(sort_col)
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        rows = list((await session.execute(rows_q)).all())
        return int(total or 0), rows

    @staticmethod
    async def get_candidate_invitation_details(
        session: AsyncSession,
        *,
        invitation_id: str,
        candidate_id: str,
    ) -> Optional[Tuple[CandidateInvitation, Job, EmployerProfile, Users, Optional[CompanyProfile], List[str]]]:
        q = (
            select(CandidateInvitation, Job, EmployerProfile, Users, CompanyProfile)
            .join(Job, Job.job_id == CandidateInvitation.job_id)
            .join(EmployerProfile, EmployerProfile.id == CandidateInvitation.employer_id)
            .join(Users, Users.user_id == EmployerProfile.user_id)
            .outerjoin(CompanyProfile, CompanyProfile.employer_id == EmployerProfile.id)
            .where(
                CandidateInvitation.invitation_id == invitation_id,
                CandidateInvitation.candidate_id == candidate_id,
            )
        )
        row = (await session.execute(q)).one_or_none()
        if not row:
            return None

        invitation, job, employer, recruiter, company = row
        skill_rows = await session.execute(
            select(JobSkill.skill)
            .where(JobSkill.job_id == job.job_id)
            .order_by(JobSkill.skill.asc())
        )
        return invitation, job, employer, recruiter, company, list(skill_rows.scalars().all())

    @staticmethod
    async def get_invitation_notification_context(
        session: AsyncSession,
        *,
        invitation_id: str,
        candidate_id: str,
    ):
        q = (
            select(CandidateInvitation, Job, EmployerProfile, Users)
            .join(Job, Job.job_id == CandidateInvitation.job_id)
            .join(EmployerProfile, EmployerProfile.id == CandidateInvitation.employer_id)
            .join(CandidateProfile, CandidateProfile.candidate_id == CandidateInvitation.candidate_id)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateInvitation.invitation_id == invitation_id,
                CandidateInvitation.candidate_id == candidate_id,
            )
        )
        return (await session.execute(q)).one_or_none()

    @staticmethod
    async def list_active_jobs_for_invitation(
        session: AsyncSession,
        *,
        employer_id: str,
        page: int,
        page_size: int,
    ) -> Tuple[int, List[Tuple[Job, int]]]:
        application_counts = (
            select(
                JobApplication.job_id.label("job_id"),
                func.count(JobApplication.application_id).label("application_count"),
            )
            .where(JobApplication.is_deleted.is_(False))
            .group_by(JobApplication.job_id)
            .subquery()
        )
        base = (
            select(Job, func.coalesce(application_counts.c.application_count, 0))
            .outerjoin(application_counts, application_counts.c.job_id == Job.job_id)
            .where(
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                Job.status == "PUBLISHED",
            )
        )
        total = await session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await session.execute(
            base.order_by(Job.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return int(total or 0), list(rows.all())

    @staticmethod
    async def mark_viewed(
        session: AsyncSession,
        *,
        invitation: CandidateInvitation,
    ) -> CandidateInvitation:
        if invitation.status not in ("PENDING",):
            return invitation
        invitation.status = "VIEWED"
        invitation.viewed_at = invitation.viewed_at or utc_now_naive()
        await session.commit()
        await session.refresh(invitation)
        return invitation

