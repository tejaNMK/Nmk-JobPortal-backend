from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume import CandidateResume
from app.model.candidate_model.candidate_resume_detail import (
    CandidateResumeDetail,
)
from app.model.candidate_model.job_application import JobApplication


class CandidateDetailsRepo:

    @classmethod
    async def get_candidate_details(
        cls,
        session: AsyncSession,
        candidate_id: str,
    ):
        query = (
            select(
                CandidateProfile,
                Users,
            )
            .join(
                Users,
                CandidateProfile.user_id == Users.user_id,
            )
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                Users.deleted_flag.is_(False),
            )
            .options(
                selectinload(
                    CandidateProfile.resumes
                ),
                selectinload(
                    CandidateProfile.resume_details
                ),
                selectinload(
                    CandidateProfile.applications
                ).selectinload(
                    JobApplication.job
                ),
                selectinload(
                    CandidateProfile.applications
                ).selectinload(
                    JobApplication.notes
                ),
                selectinload(
                    CandidateProfile.applications
                ).selectinload(
                    JobApplication.interviews
                ),
                selectinload(
                    CandidateProfile.applications
                ).selectinload(
                    JobApplication.status_history
                ),
            )
        )

        result = await session.execute(query)

        return result.first()