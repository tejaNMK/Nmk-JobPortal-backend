from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.interview_history import InterviewHistory


class InterviewHistoryRepo:

    @classmethod
    async def create_history(
        cls,
        session: AsyncSession,
        history: InterviewHistory,
        commit: bool = True,
    ) -> InterviewHistory:
        session.add(history)
        if commit:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(history)
        return history
