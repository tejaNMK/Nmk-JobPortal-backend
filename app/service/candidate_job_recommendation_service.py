from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.job import Job
from app.repository.candidate_repository.candidate_job_recommendation_repo import (
    CandidateJobRecommendationRepo,
)
from app.repository.candidate_repository.candidate_job_search_repo import (
    CandidateJobSearchRepo,
)
from app.schema.candidate_job_recommendation import (
    CandidateRecommendedJobCardResponse,
    CandidateRecommendedJobsResponse,
)
from app.service.candidate_job_recommendation_engine import (
    DEFAULT_MIN_MATCH_SCORE,
    MatchResult,
    rank_jobs_for_candidate,
)
from app.service.candidate_job_search_service import CandidateJobSearchService
from app.utils.slug import slugify_job_title


class CandidateJobRecommendationService:
    """AI-powered Recommended Jobs for the Candidate module.

    Pipeline: load the candidate's profile/skills/resume/preference signals
    -> pull the pool of active, eligible (not expired/inactive/applied) jobs
    -> score every job against the candidate with the recommendation engine
    -> persist the ranked matches to `job_recommendations` (audit trail /
    cache) -> return a paginated, enriched job-card response.

    Recommendations are always generated fresh from the candidate's current
    profile and the current job pool, so they naturally stay up to date as
    either changes — there's nothing to invalidate.
    """

    @staticmethod
    async def get_recommended_jobs(
        session: AsyncSession,
        user_id: UUID,
        *,
        location: Optional[str] = None,
        employment_type: Optional[str] = None,
        work_preference: Optional[str] = None,
        skills: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 20,
        min_match_score: float = DEFAULT_MIN_MATCH_SCORE,
    ) -> CandidateRecommendedJobsResponse:
        profile = await CandidateJobRecommendationRepo.get_candidate_profile(
            session, user_id
        )
        if not profile:
            return CandidateRecommendedJobsResponse(
                total_records=0,
                page=page,
                page_size=page_size,
                generated_at=datetime.now(timezone.utc),
                results=[],
            )

        candidate_context = await CandidateJobRecommendationRepo.build_candidate_match_context(
            session, profile
        )

        jobs, _applied_job_ids = await CandidateJobRecommendationRepo.get_eligible_job_pool(
            session, profile.candidate_id
        )

        jobs = CandidateJobRecommendationService._apply_filters(
            jobs,
            location=location,
            employment_type=employment_type,
            work_preference=work_preference,
            skills=skills,
        )

        jobs_by_id = {j.job_id: j for j in jobs}
        job_contexts = [
            CandidateJobRecommendationRepo.to_job_match_context(j) for j in jobs
        ]

        ranked: List[MatchResult] = rank_jobs_for_candidate(
            candidate_context, job_contexts, min_score=min_match_score
        )

        # Persist the current top matches for audit/analytics and so a
        # dashboard/admin view can see what a candidate was recommended
        # without recomputing.
        await CandidateJobRecommendationRepo.upsert_recommendations(
            session,
            profile.candidate_id,
            [(r.job_id, r.score) for r in ranked[:100]],
        )

        total = len(ranked)
        start = (page - 1) * page_size
        end = start + page_size
        page_slice = ranked[start:end]

        page_job_ids = [r.job_id for r in page_slice]
        saved_job_ids, apps_map = await CandidateJobSearchRepo.get_saved_and_applied_maps(
            session, user_id, page_job_ids
        )
        logo_map = await CandidateJobSearchRepo.get_company_logo_path_for_jobs(
            session, page_job_ids
        )

        results = []
        for match in page_slice:
            job = jobs_by_id.get(match.job_id)
            if not job:
                continue
            results.append(
                CandidateJobRecommendationService._to_card(
                    job,
                    match,
                    logo=logo_map.get(job.job_id),
                    is_saved=job.job_id in saved_job_ids,
                    application=apps_map.get(job.job_id),
                )
            )

        return CandidateRecommendedJobsResponse(
            total_records=total,
            page=page,
            page_size=page_size,
            generated_at=datetime.now(timezone.utc),
            results=results,
        )

    @staticmethod
    def _apply_filters(
        jobs: Sequence[Job],
        *,
        location: Optional[str],
        employment_type: Optional[str],
        work_preference: Optional[str],
        skills: Optional[List[str]],
    ) -> List[Job]:
        out = list(jobs)

        if location:
            needle = location.strip().lower()
            out = [j for j in out if j.location and needle in j.location.lower()]

        if employment_type:
            needle = employment_type.strip().upper().replace("-", "_").replace(" ", "_")
            out = [
                j
                for j in out
                if (j.employment_type or "").strip().upper().replace("-", "_").replace(" ", "_")
                == needle
            ]

        if work_preference:
            needle = work_preference.strip().upper().replace("-", "_").replace(" ", "_")
            out = [
                j
                for j in out
                if (j.work_mode or "").strip().upper().replace("-", "_").replace(" ", "_")
                == needle
            ]

        if skills:
            wanted = {s.strip().lower() for s in skills if s and s.strip()}
            if wanted:
                out = [
                    j
                    for j in out
                    if wanted & {s.skill.strip().lower() for s in (j.skills or []) if s.skill}
                ]

        return out

    @staticmethod
    def _to_card(
        job: Job,
        match: MatchResult,
        *,
        logo: Optional[str],
        is_saved: bool,
        application,
    ) -> CandidateRecommendedJobCardResponse:
        return CandidateRecommendedJobCardResponse(
            job_id=job.job_id,
            job_title=job.title,
            job_slug=slugify_job_title(job.title),
            description_preview=CandidateJobSearchService._description_preview_from_job(job),
            company_name=job.company_name,
            company_logo=logo,
            location=job.location,
            salary_range=CandidateJobSearchService._salary_range_from_job(job),
            salary_currency=job.salary_currency,
            salary_period=job.salary_period,
            employment_type=job.employment_type,
            work_preference=job.work_mode,
            experience_required=CandidateJobSearchService._experience_required_from_job(job),
            posted_date=job.created_at,
            skills=[s.skill for s in (job.skills or [])],
            is_saved=is_saved,
            already_applied=application is not None,
            application_status=application.application_status if application else None,
            match_score=match.score,
            match_percentage=round(match.score),
            match_reasons=match.reasons,
        )