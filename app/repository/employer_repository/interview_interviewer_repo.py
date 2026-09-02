from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.interviewer import Interviewer
from app.model.employer_model.interview_interviewer import (
    InterviewInterviewer,
)


class InterviewInterviewerRepo:
    @classmethod
    async def get_active_users_by_ids(cls, session, user_ids):
        return []

    @classmethod
    async def get_active_interviewer_users_by_ids(cls, session, user_ids):
        return []

    @classmethod
    async def get_active_interviewer_users_by_emails(cls, session, emails):
        return []

    @classmethod
    async def list_active_interviewers(cls, session, search, page, page_size):
        return 0, []

    @classmethod
    async def get_assigned_interviewers(
        cls,
        session: AsyncSession,
        interview_id: str,
    ):
        result = await session.execute(
            select(
                Interviewer.id,
                Interviewer.name,
                Interviewer.email,
            )
            .join(
                InterviewInterviewer,
                InterviewInterviewer.interviewer_id == Interviewer.id,
            )
            .where(
                InterviewInterviewer.interview_id == interview_id,
            )
        )

        return result.all()

    @classmethod
    async def replace_interviewers(
        cls,
        session: AsyncSession,
        interview_id: str,
        interviewer_ids: list[str],
    ) -> tuple[set[str], set[str]]:
        current_result = await session.execute(
            select(InterviewInterviewer.interviewer_id).where(
                InterviewInterviewer.interview_id == interview_id
            )
        )
        current_ids = set(current_result.scalars().all())
        requested_ids = set(interviewer_ids)

        await session.execute(
            delete(InterviewInterviewer).where(
                InterviewInterviewer.interview_id == interview_id
            )
        )

        for interviewer_id in interviewer_ids:
            session.add(
                InterviewInterviewer(
                    interview_id=interview_id,
                    interviewer_id=interviewer_id,
                )
            )

        await session.flush()
        return requested_ids - current_ids, current_ids - requested_ids

    @classmethod
    async def get_interviewer_emails(
        cls,
        session: AsyncSession,
        interview_id: str,
    ):
        result = await session.execute(
            select(
                Interviewer.id,
                Interviewer.name,
                Interviewer.email,
            )
            .join(
                InterviewInterviewer,
                InterviewInterviewer.interviewer_id == Interviewer.id,
            )
            .where(
                InterviewInterviewer.interview_id == interview_id,
                Interviewer.email.is_not(None),
            )
        )

        return result.all()
