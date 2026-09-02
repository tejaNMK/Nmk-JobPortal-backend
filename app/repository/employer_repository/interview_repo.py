from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.job import Job

from app.model.employer_model.interview import Interview


class InterviewRepo:

    @classmethod
    async def create_interview(
        cls,
        session: AsyncSession,
        interview: Interview,
        commit: bool = True,
    ):
        session.add(interview)

        if commit:
            await session.commit()
        else:
            await session.flush()

        await session.refresh(interview)

        return interview

    @classmethod
    async def get_by_application_id(
        cls,
        session: AsyncSession,
        application_id: str,
    ):
        result = await session.execute(
            select(Interview).where(
                Interview.application_id == application_id
            )
        )

        return result.scalar_one_or_none()

    @classmethod
    async def get_by_id(
        cls,
        session: AsyncSession,
        interview_id: str,
    ):
        result = await session.execute(
            select(Interview).where(
                Interview.interview_id == interview_id
            )
        )

        return result.scalar_one_or_none()
    
    @classmethod
    async def get_by_id_for_employer(
        cls,
        session: AsyncSession,
        interview_id: str,
        employer_id: str,
    ):
        """
        Returns the interview only if it belongs to a job
        owned by the employer.
        """

        result = await session.execute(
            select(Interview)
            .join(
                JobApplication,
                JobApplication.application_id == Interview.application_id,
            )
            .join(
                Job,
                Job.job_id == JobApplication.job_id,
            )
            .where(
                Interview.interview_id == interview_id,
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
            )
        )

        return result.scalar_one_or_none()

    @classmethod
    async def get_active_interview(
        cls,
        session: AsyncSession,
        application_id: str,
    ):
        """
        Returns an active interview if one already exists.
        """

        result = await session.execute(
            select(Interview).where(
                and_(
                    Interview.application_id == application_id,
                    Interview.status.in_(
                        [
                            "SCHEDULED",
                            "RESCHEDULED",
                        ]
                    ),
                )
            )
        )

        return result.scalar_one_or_none()

    @classmethod
    async def count_active_by_application(
        cls,
        session: AsyncSession,
        application_id: str,
    ) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(Interview)
            .where(
                Interview.application_id == application_id,
                Interview.status.in_(
                    [
                        "SCHEDULED",
                        "RESCHEDULED",
                    ]
                ),
            )
        )

        return result.scalar_one()

    @classmethod
    async def get_duplicate_interview(
        cls,
        session: AsyncSession,
        application_id: str,
        interview_date,
        interview_time,
        round_number=None,
    ):
        """
        Prevent duplicate active interview timeslots and duplicate round
        numbers across all interview history for the application.
        """

        criteria = [
            Interview.application_id == application_id,
        ]
        if round_number is not None:
            criteria.append(Interview.round_number == round_number)
        else:
            criteria.extend(
                [
                    Interview.status.in_(
                        [
                            "SCHEDULED",
                            "RESCHEDULED",
                        ]
                    ),
                    Interview.interview_date == interview_date,
                    Interview.interview_time == interview_time,
                ]
            )

        result = await session.execute(
            select(Interview).where(and_(*criteria))
        )

        return result.scalar_one_or_none()

    @classmethod
    async def update_interview(
        cls,
        session: AsyncSession,
        interview: Interview,
        commit: bool = True,
    ):
        session.add(interview)

        if commit:
            await session.commit()
        else:
            await session.flush()

        await session.refresh(interview)

        return interview

    @classmethod
    async def update_status(
        cls,
        session: AsyncSession,
        interview: Interview,
        status: str,
        commit: bool = True,
    ):
        interview.status = status
        if status == "COMPLETED" and interview.completed_at is None:
            interview.completed_at = utc_now_naive()

        session.add(interview)

        if commit:
            await session.commit()
        else:
            await session.flush()

        await session.refresh(interview)

        return interview

    @classmethod
    async def delete_interview(
        cls,
        session: AsyncSession,
        interview: Interview,
    ):
        await session.delete(interview)

        await session.commit()

    @classmethod
    async def get_by_application_for_employer(
        cls,
        session: AsyncSession,
        application_id: str,
        employer_id: str,
    ):
        result = await session.execute(
            select(Interview)
            .join(
                JobApplication,
                JobApplication.application_id == Interview.application_id,
            )
            .join(
                Job,
                Job.job_id == JobApplication.job_id,
            )
            .where(
                Interview.application_id == application_id,
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
                JobApplication.is_deleted.is_(False),
                Interview.status.in_(
                    [
                        "SCHEDULED",
                        "RESCHEDULED",
                        "COMPLETED",
                        "CANCELLED",
                        "NO_SHOW",
                    ]
                ),
            )
            .order_by(
                Interview.round_number.asc().nulls_last(),
                Interview.interview_date.asc(),
                Interview.interview_time.asc(),
            )
        )

        return result.scalars().all()
