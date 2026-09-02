from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.authentication.users import Users
from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume import CandidateResume
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.employer_model.candidate_ai_insight import CandidateAIInsight
from app.model.candidate_model.job_application import JobApplication
from app.model.employer_model.candidate_invitation import CandidateInvitation
from app.model.employer_model.job import Job
from app.model.employer_model.shortlisted_candidate import ShortlistedCandidate


class CandidateAIInsightsRepository:
    @staticmethod
    async def get_visible_candidate(session: AsyncSession, candidate_id: str):
        result = await session.execute(
            select(CandidateProfile, Users)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                CandidateProfile.searchable_flag.is_(True),
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
            )
        )
        return result.first()

    @staticmethod
    async def get_accessible_candidate(
        session: AsyncSession,
        *,
        candidate_id: str,
        employer_id: str,
    ):
        has_application = (
            select(JobApplication.application_id)
            .join(Job, Job.job_id == JobApplication.job_id)
            .where(
                JobApplication.candidate_id == candidate_id,
                JobApplication.is_deleted.is_(False),
                Job.employer_id == employer_id,
                Job.is_deleted.is_(False),
            )
            .limit(1)
            .exists()
        )
        has_invitation = (
            select(CandidateInvitation.invitation_id)
            .where(
                CandidateInvitation.candidate_id == candidate_id,
                CandidateInvitation.employer_id == employer_id,
            )
            .limit(1)
            .exists()
        )
        has_shortlist = (
            select(ShortlistedCandidate.shortlist_id)
            .where(
                ShortlistedCandidate.candidate_id == candidate_id,
                ShortlistedCandidate.employer_id == employer_id,
                ShortlistedCandidate.status == "ACTIVE",
            )
            .limit(1)
            .exists()
        )
        result = await session.execute(
            select(CandidateProfile, Users)
            .join(Users, Users.user_id == CandidateProfile.user_id)
            .where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
                CandidateProfile.status == "ACTIVE",
                Users.deleted_flag.is_(False),
                Users.user_status == "ACTIVE",
                or_(
                    and_(
                        CandidateProfile.searchable_flag.is_(True),
                        CandidateProfile.search_engine_indexing.is_(True),
                    ),
                    has_application,
                    has_invitation,
                    has_shortlist,
                ),
            )
        )
        return result.first()

    @staticmethod
    async def candidate_exists(session: AsyncSession, candidate_id: str) -> bool:
        result = await session.execute(
            select(CandidateProfile.candidate_id).where(
                CandidateProfile.candidate_id == candidate_id,
                CandidateProfile.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_active_resume(
        session: AsyncSession,
        *,
        candidate_id: str,
        active_resume_id: Optional[str],
    ) -> Optional[CandidateResume]:
        base = select(CandidateResume).where(
            CandidateResume.candidate_id == candidate_id,
            CandidateResume.is_deleted.is_(False),
        )
        if active_resume_id:
            result = await session.execute(base.where(CandidateResume.resume_id == active_resume_id))
            resume = result.scalar_one_or_none()
            if resume:
                return resume
        result = await session.execute(
            base.where(CandidateResume.is_archived.is_(False))
            .order_by(CandidateResume.uploaded_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_resume_detail(
        session: AsyncSession,
        candidate_id: str,
    ) -> Optional[CandidateResumeDetail]:
        result = await session.execute(
            select(CandidateResumeDetail)
            .where(
                CandidateResumeDetail.candidate_id == candidate_id,
                CandidateResumeDetail.is_deleted.is_(False),
            )
            .order_by(CandidateResumeDetail.generated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_cached_insight(
        session: AsyncSession,
        candidate_id: str,
    ) -> Optional[CandidateAIInsight]:
        result = await session.execute(
            select(CandidateAIInsight).where(CandidateAIInsight.candidate_id == candidate_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_insight(
        session: AsyncSession,
        insight: CandidateAIInsight,
    ) -> CandidateAIInsight:
        existing = await CandidateAIInsightsRepository.get_cached_insight(
            session,
            insight.candidate_id,
        )
        if not existing:
            session.add(insight)
            await session.flush()
            return insight

        for field in (
            "summary",
            "primary_skills",
            "experience_level",
            "career_focus",
            "key_strengths",
            "potential_gaps",
            "suitable_roles",
            "notable_experience",
            "education_summary",
            "certifications",
            "years_of_experience",
            "confidence",
            "source_metadata",
            "candidate_data_hash",
            "model_name",
            "prompt_version",
            "generated_at",
        ):
            setattr(existing, field, getattr(insight, field))
        session.add(existing)
        await session.flush()
        return existing
