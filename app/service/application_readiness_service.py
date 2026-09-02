"""AI Application Readiness Score service.

Combines the candidate's Candidate Profile, latest Resume, Skills, and a
single Job's details into a single 0-100 "Application Readiness Score"
made of five factors:

    - Resume Match Score       (AI  -- no existing deterministic engine)
    - Skills Match Score       (deterministic -- reused from
                                 `candidate_job_recommendation_engine.compute_skill_match`,
                                 the same engine behind `SkillMatchService`)
    - Experience Match Score   (deterministic -- reused from
                                 `candidate_job_recommendation_engine.score_job_for_candidate`,
                                 the same engine behind Job Recommendations)
    - Profile Completeness Score (deterministic -- reused from the value
                                 already maintained on
                                 `CandidateProfile.profile_completion_pct`)
    - Interview Readiness Score (AI -- no existing deterministic engine)

`overall_score` is a deterministic weighted composite of those five factors
(see `app.schema.application_readiness` WEIGHT_* constants) -- it is
computed in this service, never returned by the AI, so it can never
disagree with the sub-scores it's built from.

This service intentionally does not duplicate any existing logic:
    - Candidate/job data access reuses `CandidateJobRecommendationRepo` and
      `CandidateJobSearchRepo`, exactly as `JobMatchService` and
      `AIInterviewQuestionService` already do.
    - Candidate/job prompt-text rendering reuses
      `JobMatchService._build_candidate_text` / `._build_job_text` rather
      than re-implementing the same formatting.
    - Skill matching reuses `compute_skill_match` (shared with
      `SkillMatchService`), and experience fit reuses
      `score_job_for_candidate` (shared with `CandidateJobRecommendationService`).
    - The Bedrock call goes through the same shared `AIService` (see
      `app.service.ai_service`) used by every other candidate-side AI
      feature, including its JSON parsing/repair and error handling.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.job import Job
from app.repository.candidate_repository.candidate_job_recommendation_repo import (
    CandidateJobRecommendationRepo,
)
from app.repository.candidate_repository.candidate_job_search_repo import (
    CandidateJobSearchRepo,
)
from app.schema.application_readiness import (
    WEIGHT_EXPERIENCE_MATCH,
    WEIGHT_INTERVIEW_READINESS,
    WEIGHT_PROFILE_COMPLETENESS,
    WEIGHT_RESUME_MATCH,
    WEIGHT_SKILLS_MATCH,
    ApplicationReadinessScoreResponse,
)
from app.service.ai_service import AIService, AIServiceError, ai_error_status_code
from app.service.candidate_job_recommendation_engine import (
    WEIGHT_EXPERIENCE as ENGINE_WEIGHT_EXPERIENCE,
    compute_skill_match,
    score_job_for_candidate,
)
from app.service.job_match_service import JobMatchService

logger = logging.getLogger(__name__)


def _as_str_list(value: Any) -> List[str]:
    """Defensively coerce an AI-returned field into a clean list of
    non-empty strings -- the model's output is untrusted input even when
    prompted for strict JSON. Mirrors `job_match_service._as_str_list` so
    both AI features sanitize AI list output identically."""
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(text)
        elif isinstance(item, (int, float, bool)):
            out.append(str(item))
    return out


def _as_score(value: Any) -> float:
    """Defensively coerce an AI-returned score into a float clamped to
    [0, 100], mirroring how `JobMatchService._to_response` clamps
    `match_score`."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(100.0, score))


class ApplicationReadinessService:
    """Orchestrates the AI Application Readiness Score feature.

    `ai_service` is constructor-injected (defaulting to a real
    `AIService`) so callers/tests can supply a fake/mocked implementation
    without monkeypatching module internals -- same pattern as
    `JobMatchService` / `AIInterviewQuestionService`.
    """

    def __init__(self, ai_service: Optional[AIService] = None) -> None:
        self._ai_service = ai_service or AIService()

    async def get_application_readiness_score(
        self,
        session: AsyncSession,
        user_id: UUID,
        job_id: str,
    ) -> Optional[ApplicationReadinessScoreResponse]:
        profile = await CandidateJobRecommendationRepo.get_candidate_profile(
            session, user_id
        )
        if not profile:
            return None

        job = await CandidateJobSearchRepo.get_job_details(session, user_id, job_id)
        if not job:
            return None

        resume_detail = await CandidateJobRecommendationRepo.get_latest_resume_detail(
            session, profile.candidate_id
        )
        candidate_context = await CandidateJobRecommendationRepo.build_candidate_match_context(
            session, profile
        )
        job_context = CandidateJobRecommendationRepo.to_job_match_context(job)

        # ------------------------------------------------------------
        # Deterministic factors -- reused, not recomputed.
        # ------------------------------------------------------------
        skill_detail = compute_skill_match(
            candidate_context.skills,
            job_context.required_skills,
            job_context.preferred_skills,
        )
        skills_match_score = skill_detail.match_percentage

        match_result = score_job_for_candidate(candidate_context, job_context)
        experience_points = match_result.breakdown.get("experience", 0.0)
        experience_match_score = round(
            max(0.0, min(100.0, (experience_points / ENGINE_WEIGHT_EXPERIENCE) * 100)),
            2,
        )

        profile_completeness_score = float(
            max(0, min(100, profile.profile_completion_pct or 0))
        )

        # ------------------------------------------------------------
        # AI factors -- Resume Match Score + Interview Readiness Score,
        # plus the narrative fields (strengths/weaknesses/gaps/
        # suggestions/explanation). Reuses JobMatchService's prompt-text
        # builders instead of re-formatting candidate/job data.
        # ------------------------------------------------------------
        candidate_text = JobMatchService._build_candidate_text(
            profile, resume_detail, candidate_context.skills
        )
        job_text = JobMatchService._build_job_text(job)

        system_prompt, user_prompt = self._build_prompt(
            candidate_text,
            job_text,
            matched_skills=skill_detail.matched_skills,
            missing_skills=sorted(
                set(skill_detail.missing_required_skills)
                | set(skill_detail.missing_preferred_skills)
            ),
            deterministic_reasons=match_result.reasons,
        )

        try:
            raw = self._ai_service.invoke_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1800,
                temperature=0.2,
            )
        except AIServiceError as exc:
            logger.error(
                "AI application readiness scoring failed for job_id=%s, candidate_id=%s: %s",
                job_id,
                profile.candidate_id,
                exc,
            )
            raise HTTPException(
                status_code=ai_error_status_code(exc),
                detail=(
                    "AI application readiness scoring is temporarily "
                    "unavailable. Please try again shortly."
                ),
            ) from exc

        return self._to_response(
            job,
            raw,
            skill_detail=skill_detail,
            skills_match_score=skills_match_score,
            experience_match_score=experience_match_score,
            profile_completeness_score=profile_completeness_score,
        )

    # ------------------------------------------------------------------
    # Prompt engineering
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        candidate_text: str,
        job_text: str,
        *,
        matched_skills: List[str],
        missing_skills: List[str],
        deterministic_reasons: List[str],
    ) -> tuple[str, str]:
        system_prompt = (
            "You are an expert career coach and ATS (Applicant Tracking "
            "System) analyst. You assess how ready a candidate is to apply "
            "to, and interview for, a specific job -- based on their "
            "profile, resume, and the job's requirements.\n\n"
            "Two factors have already been computed deterministically and "
            "are provided to you as grounding context -- matched skills, "
            "missing skills, and other deterministic match signals. Do not "
            "recompute or contradict them; use them to inform your "
            "analysis.\n\n"
            "You MUST respond with ONLY a single valid JSON object and "
            "nothing else -- no markdown, no code fences, no explanations "
            "before or after the JSON. The JSON object must contain "
            "exactly these keys:\n"
            '- "resume_match_score": integer from 0 to 100, how well the '
            "candidate's resume content (wording, depth, achievements, "
            "structure) aligns with what this job is looking for.\n"
            '- "interview_readiness_score": integer from 0 to 100, how '
            "prepared the candidate appears to be for an interview for "
            "this job, based on the depth and clarity of their profile "
            "and resume (e.g. quantified achievements, relevant project "
            "detail, clear career narrative).\n"
            '- "strengths": array of strings, the candidate\'s strengths '
            "relevant to this job.\n"
            '- "weaknesses": array of strings, the candidate\'s gaps or '
            "weaknesses relevant to this job.\n"
            '- "gaps": array of strings, readiness gaps that are NOT '
            "about missing skills (missing skills are already handled "
            "deterministically) -- e.g. thin resume detail, missing "
            "certifications, unclear career narrative, or interview "
            "preparation gaps.\n"
            '- "improvement_suggestions": array of strings, concrete '
            "actions the candidate could take to improve their readiness "
            "to apply for and interview for this job.\n"
            '- "readiness_explanation": string, 2-4 sentences giving a '
            "concise, human-readable explanation of the candidate's "
            "overall readiness for this job.\n\n"
            "Base your analysis strictly on the candidate and job "
            "information provided below. If information is missing or "
            "unclear, make a reasonable, conservative assessment instead "
            "of inventing facts. Return valid JSON only, with no trailing "
            "commentary."
        )

        deterministic_lines = [
            f"Matched skills (already computed): {', '.join(matched_skills) or 'none'}",
            f"Missing skills (already computed): {', '.join(missing_skills) or 'none'}",
        ]
        if deterministic_reasons:
            deterministic_lines.append("Other deterministic match signals:")
            deterministic_lines.extend(f"- {r}" for r in deterministic_reasons)

        user_prompt = (
            "CANDIDATE PROFILE AND RESUME:\n"
            f"{candidate_text}\n\n"
            "JOB DESCRIPTION:\n"
            f"{job_text}\n\n"
            "DETERMINISTIC MATCH CONTEXT:\n"
            f"{chr(10).join(deterministic_lines)}\n\n"
            "Assess this candidate's application readiness for this job "
            "and respond with the JSON object described in your "
            "instructions."
        )
        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # Response mapping / validation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(
        job: Job,
        raw: Dict[str, Any],
        *,
        skill_detail,
        skills_match_score: float,
        experience_match_score: float,
        profile_completeness_score: float,
    ) -> ApplicationReadinessScoreResponse:
        resume_match_score = round(_as_score(raw.get("resume_match_score")), 2)
        interview_readiness_score = round(
            _as_score(raw.get("interview_readiness_score")), 2
        )

        explanation = raw.get("readiness_explanation")
        explanation_text = explanation.strip() if isinstance(explanation, str) else ""

        overall_score = round(
            max(
                0.0,
                min(
                    100.0,
                    (
                        resume_match_score * WEIGHT_RESUME_MATCH
                        + skills_match_score * WEIGHT_SKILLS_MATCH
                        + experience_match_score * WEIGHT_EXPERIENCE_MATCH
                        + profile_completeness_score * WEIGHT_PROFILE_COMPLETENESS
                        + interview_readiness_score * WEIGHT_INTERVIEW_READINESS
                    )
                    / 100.0,
                ),
            ),
            2,
        )

        missing_skills = sorted(
            set(skill_detail.missing_required_skills)
            | set(skill_detail.missing_preferred_skills)
        )

        return ApplicationReadinessScoreResponse(
            job_id=job.job_id,
            job_title=job.title,
            overall_score=overall_score,
            resume_match_score=resume_match_score,
            skills_match_score=round(skills_match_score, 2),
            experience_match_score=round(experience_match_score, 2),
            profile_completeness_score=round(profile_completeness_score, 2),
            interview_readiness_score=interview_readiness_score,
            matched_skills=skill_detail.matched_skills,
            missing_skills=missing_skills,
            strengths=_as_str_list(raw.get("strengths")),
            weaknesses=_as_str_list(raw.get("weaknesses")),
            gaps=_as_str_list(raw.get("gaps")),
            improvement_suggestions=_as_str_list(raw.get("improvement_suggestions")),
            readiness_explanation=explanation_text,
        )