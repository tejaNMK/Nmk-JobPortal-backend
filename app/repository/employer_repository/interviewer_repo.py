from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.interviewer import Interviewer
from app.model.employer_model.interview_interviewer import InterviewInterviewer


class InterviewerRepo:
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        interviewer: Interviewer,
    ) -> Interviewer:
        session.add(interviewer)
        await session.flush()
        await session.refresh(interviewer)
        return interviewer

    @classmethod
    async def get_by_id(
        cls,
        session: AsyncSession,
        interviewer_id: str,
    ) -> Interviewer | None:
        result = await session.execute(
            select(Interviewer).where(Interviewer.id == interviewer_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_email(
        cls,
        session: AsyncSession,
        email: str,
    ) -> Interviewer | None:
        result = await session.execute(
            select(Interviewer).where(func.lower(Interviewer.email) == email)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def get_by_emails(
        cls,
        session: AsyncSession,
        emails: list[str],
    ) -> list[Interviewer]:
        if not emails:
            return []

        result = await session.execute(
            select(Interviewer).where(func.lower(Interviewer.email).in_(emails))
        )
        return result.scalars().all()

    @classmethod
    async def list(
        cls,
        session: AsyncSession,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[int, list[Interviewer]]:
        query = select(Interviewer)

        if search:
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Interviewer.name.ilike(term),
                    Interviewer.email.ilike(term),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_query)).scalar_one()

        result = await session.execute(
            query.order_by(Interviewer.name.asc(), Interviewer.email.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return total, result.scalars().all()

    @classmethod
    async def delete(
        cls,
        session: AsyncSession,
        interviewer: Interviewer,
    ) -> None:
        await session.delete(interviewer)
        await session.flush()

    @classmethod
    async def count_interview_assignments(
        cls,
        session: AsyncSession,
        interviewer_id: str,
    ) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(InterviewInterviewer)
            .where(InterviewInterviewer.interviewer_id == interviewer_id)
        )
        return result.scalar_one()
