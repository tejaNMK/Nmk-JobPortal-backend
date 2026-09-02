from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import commit_rollback
from app.model.employer_model.ai_candidate_match import AICandidateMatch
from app.repository.employer_repository.ai_candidate_matching_repo import (
    AICandidateMatchingRepository,
)
from app.repository.subscription.user_subscription_repo import UserSubscriptionRepository
from app.schema.employer_ai_candidate_matching import (
    AI_CANDIDATE_ANALYSIS_LIMIT_KEY,
    AI_CANDIDATE_MATCHING_FEATURE_KEY,
    AI_CANDIDATE_MATCHING_RUN_LIMIT_KEY,
    AICandidateMatchFilters,
    AICandidateMatchListResponse,
    AICandidateMatchRunRequest,
    AICandidateMatchRunResponse,
    CandidateMatchDetail,
    CandidateMatchResult,
    ExperienceMatch,
)
from app.service.employer_service.ai_candidate_matching_engine import (
    SCORING_VERSION,
    CandidateMatchInput,
    JobMatchInput,
    match_level,
    normalize_skills,
    score_candidate_for_job,
)
from app.service.subscription.subscription_validator import SubscriptionValidator
from app.utils.image_urls import resolve_profile_image_url


def _full_name(user) -> str:
    return " ".join(
        part
        for part in (
            getattr(user, "first_name", None),
            getattr(user, "middle_name", None),
            getattr(user, "last_name", None),
        )
        if part
    ) or "Candidate"


def _list_from_json(value: Any, key: str) -> list:
    if isinstance(value, dict):
        raw = value.get(key)
    elif isinstance(value, list):
        raw = value
    else:
        raw = None
    return raw if isinstance(raw, list) else []


def _string_values(items: list, *keys: str) -> list[str]:
    values: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
        elif isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if value:
                    values.append(str(value).strip())
                    break
    return values


def _candidate_skills(profile, resume_detail) -> set[str]:
    values: list[str] = []
    if resume_detail:
        values.extend(
            _string_values(
                _list_from_json(resume_detail.skills_json, "skills"),
                "name",
                "skill",
                "title",
            )
        )
    if getattr(profile, "skills_summary", None):
        for part in str(profile.skills_summary).replace(";", ",").split(","):
            if part.strip():
                values.append(part.strip())
    return normalize_skills(values)


def _education_values(resume_detail) -> list[str]:
    if not resume_detail:
        return []
    return _string_values(
        _list_from_json(resume_detail.education_json, "education"),
        "degree",
        "qualification",
        "institution",
        "school",
        "university",
    )


def _certification_values(resume_detail) -> list[str]:
    if not resume_detail:
        return []
    return _string_values(
        _list_from_json(resume_detail.certifications_json, "certifications"),
        "name",
        "title",
        "certification",
    )


def _experience_titles(resume_detail) -> list[str]:
    if not resume_detail:
        return []
    return _string_values(
        _list_from_json(resume_detail.experience_json, "experience"),
        "designation",
        "role",
        "title",
    )


def _project_values(resume_detail) -> list[str]:
    if not resume_detail:
        return []
    return _string_values(
        _list_from_json(resume_detail.projects_json, "projects"),
        "name",
        "title",
        "description",
    )


def _job_input(job) -> JobMatchInput:
    job_skills = normalize_skills([skill.skill for skill in (job.skills or []) if skill.skill])
    requirement_text = list(job.requirements or [])
    preferred_lines = [
        item
        for item in requirement_text
        if any(marker in item.lower() for marker in ("preferred", "nice to have", "plus"))
    ]
    return JobMatchInput(
        job_id=job.job_id,
        title=job.title or "",
        description=job.description or "",
        required_skills=job_skills,
        preferred_skills=normalize_skills(preferred_lines),
        experience_min=job.experience_min,
        experience_max=job.experience_max,
        education=job.education,
        location=job.location or job.office_location,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        industry=job.job_category,
        requirements=requirement_text,
        responsibilities=list(job.responsibilities or []),
    )


def _candidate_input(profile, user, resume_detail, application) -> CandidateMatchInput:
    return CandidateMatchInput(
        candidate_id=profile.candidate_id,
        candidate_name=_full_name(user),
        skills=_candidate_skills(profile, resume_detail),
        total_experience_years=float(profile.total_experience)
        if profile.total_experience is not None
        else None,
        headline=profile.headline,
        summary=profile.summary,
        current_company=profile.current_company,
        target_roles=profile.target_roles,
        current_location=profile.current_location,
        preferred_location=profile.preferred_location,
        work_preference=profile.work_preference,
        desired_employment=profile.desired_employment,
        education=_education_values(resume_detail),
        certifications=_certification_values(resume_detail),
        job_titles=_experience_titles(resume_detail),
        projects=_project_values(resume_detail),
        application_id=getattr(application, "application_id", None),
        source_type="Applicant" if application else "AI Recommended Candidate",
    )


def _is_stale(match, profile, job=None, resume_detail=None) -> bool:
    if match.scoring_version != SCORING_VERSION:
        return True
    if match.job_updated_at and job and job.updated_at and job.updated_at > match.job_updated_at:
        return True
    if match.candidate_updated_at and profile.updated_at and profile.updated_at > match.candidate_updated_at:
        return True
    if (
        match.resume_generated_at
        and resume_detail
        and resume_detail.generated_at
        and resume_detail.generated_at > match.resume_generated_at
    ):
        return True
    return False


def _result(match, profile, user, job=None, resume_detail=None) -> CandidateMatchResult:
    return CandidateMatchResult(
        candidate_id=match.candidate_id,
        candidate_name=_full_name(user),
        profile_image_url=resolve_profile_image_url(
            getattr(user, "profile_image_url", None)
        ),
        match_score=round(match.overall_score),
        match_level=match_level(match.overall_score),
        source_type=match.source_type,
        application_id=match.application_id,
        matched_skills=list(match.matched_skills or []),
        missing_required_skills=list(match.missing_required_skills or []),
        matched_preferred_skills=list(match.matched_preferred_skills or []),
        experience_match=ExperienceMatch(
            candidate_years=float(profile.total_experience)
            if profile.total_experience is not None
            else None,
            required_years=(match.hard_requirements or {}).get("experience_min"),
            maximum_years=(match.hard_requirements or {}).get("experience_max"),
            score=round((match.experience_score / 25) * 100, 2) if match.experience_score is not None else 0,
        ),
        strengths=list(match.strengths or []),
        gaps=list(match.gaps or []),
        ai_summary=match.ai_summary,
        recommendation=match.recommendation,
        is_stale=_is_stale(match, profile, job, resume_detail),
        generated_at=match.updated_at or match.created_at,
    )


class AICandidateMatchingService:
    @staticmethod
    async def _employer_id(session: AsyncSession, user_id: UUID) -> str:
        employer_id = await AICandidateMatchingRepository.get_employer_id(session, user_id)
        if not employer_id:
            raise HTTPException(status_code=403, detail="Employer profile not found")
        return employer_id

    @staticmethod
    async def _enforce_subscription(session: AsyncSession, user_id: UUID, analyses: int | None = None):
        validator = SubscriptionValidator(session=session, user_id=user_id, role="EMPLOYER")
        await validator.require_feature(AI_CANDIDATE_MATCHING_FEATURE_KEY)
        await validator.ensure_limit_available(
            AI_CANDIDATE_MATCHING_RUN_LIMIT_KEY,
            period="month",
        )
        if analyses:
            await validator.ensure_limit_available(
                AI_CANDIDATE_ANALYSIS_LIMIT_KEY,
                amount=analyses,
                period="month",
            )
        return validator

    @staticmethod
    async def generate_matches(
        *,
        session: AsyncSession,
        payload: dict,
        job_id: str,
        request: AICandidateMatchRunRequest,
    ) -> AICandidateMatchRunResponse:
        user_id = UUID(str(payload.get("user_id")))
        employer_id = await AICandidateMatchingService._employer_id(session, user_id)
        validator = await AICandidateMatchingService._enforce_subscription(session, user_id)
        job = await AICandidateMatchingRepository.get_owned_job(
            session,
            employer_id=employer_id,
            job_id=job_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if not (job.description or job.skills or job.requirements):
            raise HTTPException(
                status_code=400,
                detail="Job has insufficient requirements for AI candidate matching.",
            )

        rows = await AICandidateMatchingRepository.get_candidate_pool(
            session,
            employer_id=employer_id,
            job_id=job_id,
            scope=request.scope,
            limit=request.candidate_limit,
        )
        if not rows:
            return AICandidateMatchRunResponse(
                job_id=job_id,
                total_candidates_considered=0,
                total_matches_generated=0,
                scoring_version=SCORING_VERSION,
                items=[],
            )

        await validator.ensure_limit_available(
            AI_CANDIDATE_ANALYSIS_LIMIT_KEY,
            amount=len(rows),
            period="month",
        )
        job_context = _job_input(job)
        persisted: list[tuple[AICandidateMatch, Any, Any]] = []
        for profile, user, resume_detail, application in rows:
            candidate_context = _candidate_input(profile, user, resume_detail, application)
            score = score_candidate_for_job(candidate_context, job_context)
            if request.min_score is not None and score.overall_score < request.min_score:
                continue
            match = AICandidateMatch(
                job_id=job_id,
                candidate_id=profile.candidate_id,
                application_id=getattr(application, "application_id", None),
                source_type=candidate_context.source_type,
                overall_score=score.overall_score,
                skills_score=score.skills_score,
                experience_score=score.experience_score,
                title_domain_score=score.title_domain_score,
                education_score=score.education_score,
                location_score=score.location_score,
                preferred_skills_score=score.preferred_skills_score,
                semantic_score=score.semantic_score,
                matched_skills=score.matched_skills,
                missing_required_skills=score.missing_required_skills,
                matched_preferred_skills=score.matched_preferred_skills,
                strengths=score.strengths,
                gaps=score.gaps,
                hard_requirements=score.hard_requirements,
                preferred_requirements=score.preferred_requirements,
                semantic_signals=score.semantic_signals,
                ai_summary=score.ai_summary,
                recommendation=score.recommendation,
                scoring_version=SCORING_VERSION,
                job_updated_at=job.updated_at,
                candidate_updated_at=profile.updated_at,
                resume_generated_at=getattr(resume_detail, "generated_at", None),
            )
            saved = await AICandidateMatchingRepository.upsert_match(session, match)
            persisted.append((saved, profile, user))

        user_subscription = await validator.validate_active_subscription()
        period_start, period_end = SubscriptionValidator._period_window("month")
        await UserSubscriptionRepository.increment_usage(
            session=session,
            user_subscription_id=user_subscription.user_subscription_id,
            user_id=user_id,
            feature_name=AI_CANDIDATE_MATCHING_RUN_LIMIT_KEY,
            amount=1,
            period_start=period_start,
            period_end=period_end,
            commit=False,
        )
        await UserSubscriptionRepository.increment_usage(
            session=session,
            user_subscription_id=user_subscription.user_subscription_id,
            user_id=user_id,
            feature_name=AI_CANDIDATE_ANALYSIS_LIMIT_KEY,
            amount=len(rows),
            period_start=period_start,
            period_end=period_end,
            commit=False,
        )
        await commit_rollback(session)

        items = sorted(
            [_result(match, profile, user, job, None) for match, profile, user in persisted],
            key=lambda item: (-item.match_score, item.candidate_id),
        )
        return AICandidateMatchRunResponse(
            job_id=job_id,
            total_candidates_considered=len(rows),
            total_matches_generated=len(items),
            scoring_version=SCORING_VERSION,
            items=items[:100],
        )

    @staticmethod
    async def list_matches(
        *,
        session: AsyncSession,
        payload: dict,
        job_id: str,
        filters: AICandidateMatchFilters,
    ) -> AICandidateMatchListResponse:
        user_id = UUID(str(payload.get("user_id")))
        employer_id = await AICandidateMatchingService._employer_id(session, user_id)
        job = await AICandidateMatchingRepository.get_owned_job(
            session,
            employer_id=employer_id,
            job_id=job_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        total, rows = await AICandidateMatchingRepository.list_matches(
            session,
            employer_id=employer_id,
            job_id=job_id,
            filters=filters,
        )
        return AICandidateMatchListResponse(
            job_id=job_id,
            page=filters.page,
            page_size=filters.page_size,
            total_records=total,
            items=[
                _result(match, profile, user, job, resume_detail)
                for match, profile, user, job, resume_detail in rows
            ],
        )

    @staticmethod
    async def get_match_detail(
        *,
        session: AsyncSession,
        payload: dict,
        job_id: str,
        candidate_id: str,
    ) -> CandidateMatchDetail:
        user_id = UUID(str(payload.get("user_id")))
        employer_id = await AICandidateMatchingService._employer_id(session, user_id)
        row = await AICandidateMatchingRepository.get_match_detail(
            session,
            employer_id=employer_id,
            job_id=job_id,
            candidate_id=candidate_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="AI candidate match not found")
        match, profile, user, job, resume_detail = row
        base = _result(match, profile, user, job, resume_detail)
        return CandidateMatchDetail(
            **base.model_dump(),
            hard_requirements=match.hard_requirements or {},
            preferred_requirements=match.preferred_requirements or {},
            semantic_signals=match.semantic_signals or {},
            scoring_version=match.scoring_version,
        )
