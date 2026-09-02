from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.candidate_repository.candidate_job_recommendation_repo import (
    CandidateJobRecommendationRepo,
)
from app.repository.candidate_repository.candidate_job_search_repo import (
    CandidateJobSearchRepo,
)
from app.schema.skill_match import SkillMatchResponse
from app.service.candidate_job_recommendation_engine import compute_skill_match


class SkillMatchService:
    """API-AI-002 — Skill Matching Service.

    Standalone skill-comparison API: given a candidate and a single job,
    returns which of the job's skills the candidate already has, which are
    missing, and an overall skill-match percentage.

    Shares its scoring logic (`compute_skill_match`) with the skills factor
    of the Job Recommendation Service (API-AI-003) via
    `candidate_job_recommendation_engine.py`, so the two APIs never
    disagree with each other about what counts as a skill match.
    """

    @staticmethod
    async def get_skill_match(
        session: AsyncSession,
        user_id: UUID,
        job_id: str,
    ) -> Optional[SkillMatchResponse]:
        profile = await CandidateJobRecommendationRepo.get_candidate_profile(
            session, user_id
        )
        if not profile:
            return None

        job = await CandidateJobSearchRepo.get_job_details(session, user_id, job_id)
        if not job:
            return None

        candidate_context = await CandidateJobRecommendationRepo.build_candidate_match_context(
            session, profile
        )
        job_context = CandidateJobRecommendationRepo.to_job_match_context(job)

        detail = compute_skill_match(
            candidate_context.skills,
            job_context.required_skills,
            job_context.preferred_skills,
        )

        return SkillMatchResponse(
            job_id=job.job_id,
            job_title=job.title,
            match_percentage=detail.match_percentage,
            matched_skills=detail.matched_skills,
            missing_required_skills=detail.missing_required_skills,
            missing_preferred_skills=detail.missing_preferred_skills,
            extra_skills=detail.extra_skills,
            required_skills=detail.required_skills,
            preferred_skills=detail.preferred_skills,
        )