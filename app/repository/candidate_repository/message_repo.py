from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.job_application import JobApplication
from app.model.candidate_model.message import Message
from app.model.candidate_model.message_thread import MessageThread
from app.model.employer_model.candidate_invitation import CandidateInvitation
from app.model.employer_model.company_profile import CompanyProfile
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job import Job


class MessageRepo:

    # ── Candidate resolution ────────────────────────────────────────────────
    @classmethod
    async def get_candidate_profile(cls, session: AsyncSession, user_id: UUID) -> Optional[CandidateProfile]:
        result = await session.execute(
            select(CandidateProfile).where(
                CandidateProfile.user_id == user_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    # ── Thread listing ──────────────────────────────────────────────────────
    @classmethod
    async def list_thread_ids_for_user(
        cls,
        session: AsyncSession,
        user_id: UUID,
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> Tuple[List[str], int]:
        """Threads the user participates in, ordered by most recent activity."""
        last_activity = (
            select(
                Message.thread_id.label("thread_id"),
                func.max(Message.sent_at).label("last_at"),
            )
            .where(
                or_(Message.sender_id == user_id, Message.receiver_id == user_id),
                Message.is_deleted.is_(False),
            )
            .group_by(Message.thread_id)
            .subquery()
        )

        base_query = select(last_activity.c.thread_id, last_activity.c.last_at).select_from(last_activity)

        if search:
            like = f"%{search.strip()}%"
            base_query = (
                select(last_activity.c.thread_id, last_activity.c.last_at)
                .select_from(last_activity)
                .join(MessageThread, MessageThread.thread_id == last_activity.c.thread_id)
                .where(MessageThread.subject.ilike(like))
            )

        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await session.execute(count_query)).scalar_one() or 0

        rows_query = (
            base_query.order_by(desc("last_at"))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await session.execute(rows_query)).all()
        return [row.thread_id for row in rows], total

    @classmethod
    async def get_threads_by_ids(cls, session: AsyncSession, thread_ids: Sequence[str]) -> Dict[str, MessageThread]:
        if not thread_ids:
            return {}
        result = await session.execute(
            select(MessageThread).where(MessageThread.thread_id.in_(thread_ids))
        )
        return {t.thread_id: t for t in result.scalars().all()}

    @classmethod
    async def get_last_messages_for_threads(
        cls, session: AsyncSession, thread_ids: Sequence[str]
    ) -> Dict[str, Message]:
        if not thread_ids:
            return {}
        result = await session.execute(
            select(Message)
            .where(Message.thread_id.in_(thread_ids), Message.is_deleted.is_(False))
            .order_by(Message.thread_id, desc(Message.sent_at))
        )
        latest: Dict[str, Message] = {}
        for msg in result.scalars().all():
            if msg.thread_id not in latest:
                latest[msg.thread_id] = msg
        return latest

    @classmethod
    async def get_unread_counts_for_threads(
        cls, session: AsyncSession, thread_ids: Sequence[str], user_id: UUID
    ) -> Dict[str, int]:
        if not thread_ids:
            return {}
        result = await session.execute(
            select(Message.thread_id, func.count(Message.message_id))
            .where(
                Message.thread_id.in_(thread_ids),
                Message.receiver_id == user_id,
                Message.read_flag.is_(False),
                Message.is_deleted.is_(False),
            )
            .group_by(Message.thread_id)
        )
        return {row[0]: row[1] for row in result.all()}

    @classmethod
    async def count_total_unread(cls, session: AsyncSession, user_id: UUID) -> int:
        result = await session.execute(
            select(func.count(Message.message_id)).where(
                Message.receiver_id == user_id,
                Message.read_flag.is_(False),
                Message.is_deleted.is_(False),
            )
        )
        return result.scalar_one() or 0

    @classmethod
    async def get_other_party_ids_for_threads(
        cls, session: AsyncSession, thread_ids: Sequence[str], user_id: UUID
    ) -> Dict[str, Optional[UUID]]:
        """For each thread, the counterpart user_id (None if system/unknown)."""
        if not thread_ids:
            return {}
        result = await session.execute(
            select(Message.thread_id, Message.sender_id, Message.receiver_id).where(
                Message.thread_id.in_(thread_ids),
                Message.is_deleted.is_(False),
            )
        )
        other_by_thread: Dict[str, Optional[UUID]] = {}
        for thread_id, sender_id, receiver_id in result.all():
            for party in (sender_id, receiver_id):
                if party is not None and party != user_id:
                    other_by_thread.setdefault(thread_id, party)
        for thread_id in thread_ids:
            other_by_thread.setdefault(thread_id, None)
        return other_by_thread

    # ── Employer / company lookups ──────────────────────────────────────────
    @classmethod
    async def get_employer_company_by_user_ids(
        cls, session: AsyncSession, user_ids: Sequence[UUID]
    ) -> Dict[UUID, Tuple[EmployerProfile, Optional[CompanyProfile], Optional[Users]]]:
        clean_ids = [uid for uid in set(user_ids) if uid is not None]
        if not clean_ids:
            return {}
        result = await session.execute(
            select(EmployerProfile, CompanyProfile, Users)
            .join(Users, Users.user_id == EmployerProfile.user_id)
            .outerjoin(CompanyProfile, CompanyProfile.employer_id == EmployerProfile.id)
            .where(EmployerProfile.user_id.in_(clean_ids))
        )
        mapping: Dict[UUID, Tuple[EmployerProfile, Optional[CompanyProfile], Optional[Users]]] = {}
        for employer, company, user in result.all():
            mapping[employer.user_id] = (employer, company, user)
        return mapping

    @classmethod
    async def get_employer_company_by_user_id(
        cls, session: AsyncSession, user_id: UUID
    ) -> Optional[Tuple[EmployerProfile, Optional[CompanyProfile], Optional[Users]]]:
        mapping = await cls.get_employer_company_by_user_ids(session, [user_id])
        return mapping.get(user_id)

    @classmethod
    async def get_employer_company_by_company_id(
        cls, session: AsyncSession, company_id: str
    ) -> Optional[Tuple[EmployerProfile, CompanyProfile, Optional[Users]]]:
        # NOTE: intentionally no is_public filter here. This lookup backs
        # compose(), which is only reachable after
        # candidate_has_connection_to_company() has already confirmed the
        # candidate applied to or was invited by this company — that's the
        # real authorization check. is_public gates public company *browsing*
        # and defaults to False, so requiring it here would 404 messaging for
        # the vast majority of companies even when the candidate has a
        # legitimate, already-verified connection to them.
        result = await session.execute(
            select(EmployerProfile, CompanyProfile, Users)
            .join(CompanyProfile, CompanyProfile.employer_id == EmployerProfile.id)
            .join(Users, Users.user_id == EmployerProfile.user_id)
            .where(CompanyProfile.company_id == company_id)
        )
        row = result.first()
        return tuple(row) if row else None

    @classmethod
    async def get_users_by_ids(cls, session: AsyncSession, user_ids: Sequence[UUID]) -> Dict[UUID, Users]:
        clean_ids = [uid for uid in set(user_ids) if uid is not None]
        if not clean_ids:
            return {}
        result = await session.execute(select(Users).where(Users.user_id.in_(clean_ids)))
        return {u.user_id: u for u in result.scalars().all()}

    # ── Candidate <-> company connection check (for compose) ────────────────

    @classmethod
    async def candidate_has_connection_to_company(
        cls, session: AsyncSession, candidate_id: str, company_id: str
    ) -> bool:
        applied = await session.execute(
            select(func.count(JobApplication.application_id))
            .select_from(JobApplication)
            .join(Job, Job.job_id == JobApplication.job_id)
            .join(CompanyProfile, CompanyProfile.employer_id == Job.employer_id)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
                CompanyProfile.company_id == company_id,
            )
        )
        if (applied.scalar_one() or 0) > 0:
            return True

        invited = await session.execute(
            select(func.count(CandidateInvitation.invitation_id))
            .select_from(CandidateInvitation)
            .join(CompanyProfile, CompanyProfile.employer_id == CandidateInvitation.employer_id)
            .where(
                CandidateInvitation.candidate_id == candidate_id,
                CompanyProfile.company_id == company_id,
            )
        )
        return (invited.scalar_one() or 0) > 0

    @classmethod
    async def get_messageable_companies(
        cls, session: AsyncSession, candidate_id: str
    ) -> List[CompanyProfile]:
        """Companies the candidate can start a new conversation with — i.e.
        companies whose jobs the candidate has applied to, or who have
        invited the candidate directly."""
        applied = select(CompanyProfile).select_from(CompanyProfile).join(
            Job, Job.employer_id == CompanyProfile.employer_id
        ).join(
            JobApplication, JobApplication.job_id == Job.job_id
        ).where(
            JobApplication.candidate_id == candidate_id,
            JobApplication.is_deleted.is_(False),
        )

        invited = select(CompanyProfile).select_from(CompanyProfile).join(
            CandidateInvitation, CandidateInvitation.employer_id == CompanyProfile.employer_id
        ).where(
            CandidateInvitation.candidate_id == candidate_id,
        )

        applied_result = await session.execute(applied)
        invited_result = await session.execute(invited)

        by_id: Dict[str, CompanyProfile] = {}
        for company in [*applied_result.scalars().all(), *invited_result.scalars().all()]:
            by_id.setdefault(company.company_id, company)

        return sorted(by_id.values(), key=lambda c: c.company_name.lower())

    # ── Messages / threads mutation ─────────────────────────────────────────
    @classmethod
    async def get_messages_for_thread(cls, session: AsyncSession, thread_id: str) -> List[Message]:
        result = await session.execute(
            select(Message)
            .where(Message.thread_id == thread_id, Message.is_deleted.is_(False))
            .order_by(Message.sent_at.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_thread(cls, session: AsyncSession, thread_id: str) -> Optional[MessageThread]:
        result = await session.execute(
            select(MessageThread).where(MessageThread.thread_id == thread_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def user_is_participant(cls, session: AsyncSession, thread_id: str, user_id: UUID) -> bool:
        result = await session.execute(
            select(func.count(Message.message_id)).where(
                Message.thread_id == thread_id,
                or_(Message.sender_id == user_id, Message.receiver_id == user_id),
            )
        )
        return (result.scalar_one() or 0) > 0

    @classmethod
    async def create_thread(cls, session: AsyncSession, subject: str) -> MessageThread:
        thread = MessageThread(subject=subject)
        session.add(thread)
        await session.flush()
        return thread

    @classmethod
    async def create_message(
        cls,
        session: AsyncSession,
        thread_id: str,
        sender_id: Optional[UUID],
        receiver_id: Optional[UUID],
        body: str,
    ) -> Message:
        message = Message(
            thread_id=thread_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_body=body,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message

    @classmethod
    async def mark_thread_read(cls, session: AsyncSession, thread_id: str, user_id: UUID) -> int:
        result = await session.execute(
            update(Message)
            .where(
                Message.thread_id == thread_id,
                Message.receiver_id == user_id,
                Message.read_flag.is_(False),
                Message.is_deleted.is_(False),
            )
            .values(read_flag=True)
        )
        await session.commit()
        return result.rowcount or 0

    @classmethod
    async def mark_all_read(cls, session: AsyncSession, user_id: UUID) -> int:
        result = await session.execute(
            update(Message)
            .where(
                Message.receiver_id == user_id,
                Message.read_flag.is_(False),
                Message.is_deleted.is_(False),
            )
            .values(read_flag=True)
        )
        await session.commit()
        return result.rowcount or 0