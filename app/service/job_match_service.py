"""AI Job Match Score service.

Uses AWS Bedrock (via `AIService`) to produce a rich, generative
compatibility analysis between the logged-in candidate (profile + latest
resume) and a single job: an overall 0-100 match score, matching/missing
skills, an experience-fit analysis, strengths, weaknesses, a hiring
recommendation, and improvement suggestions.

Deterministic skill-set overlap already has a dedicated, fully-tested
engine (`candidate_job_recommendation_engine.compute_skill_match`, used by
`SkillMatchService` / the `/jobs/{job_id}/skill-match` API). This service
does not duplicate that scoring logic -- it reuses the same candidate/job
data-access helpers (`CandidateJobRecommendationRepo`,
`CandidateJobSearchRepo`) and reuses the same normalized skill set for
grounding the AI prompt, but the match score, experience analysis,
strengths/weaknesses, and recommendation here are Bedrock-generated, not
locally computed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.candidate_model.candidate_profile import CandidateProfile
from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
from app.model.employer_model.job import Job
from app.repository.candidate_repository.candidate_job_recommendation_repo import (
    CandidateJobRecommendationRepo,
)
from app.repository.candidate_repository.candidate_job_search_repo import (
    CandidateJobSearchRepo,
)
from app.schema.job_match import HIRING_RECOMMENDATIONS, JobMatchScoreResponse
from app.service.ai_service import AIService, AIServiceError

logger = logging.getLogger(__name__)

_VALID_RECOMMENDATIONS = set(HIRING_RECOMMENDATIONS)


def _as_str_list(value: Any) -> List[str]:
    """Defensively coerce an AI-returned field into a clean list of
    non-empty strings, since the model's output is untrusted input even
    when prompted for strict JSON."""
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


class JobMatchService:
    """Orchestrates the AI Job Match Score feature.

    `ai_service` is constructor-injected (defaulting to a real
    `AIService`) so callers/tests can supply a fake/mocked implementation
    without monkeypatching module internals.
    """

    def __init__(self, ai_service: Optional[AIService] = None) -> None:
        self._ai_service = ai_service or AIService()

    async def get_job_match_score(
        self,
        session: AsyncSession,
        user_id: UUID,
        job_id: str,
    ) -> Optional[JobMatchScoreResponse]:
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

        candidate_text = self._build_candidate_text(
            profile, resume_detail, candidate_context.skills
        )
        job_text = self._build_job_text(job)

        system_prompt, user_prompt = self._build_prompt(candidate_text, job_text)

        try:
            raw = self._ai_service.invoke_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1800,
                temperature=0.2,
            )
        except AIServiceError as exc:
            logger.error(
                "AI job match scoring failed for job_id=%s, candidate_id=%s: %s",
                job_id,
                profile.candidate_id,
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail="AI job match scoring is temporarily unavailable. Please try again shortly.",
            ) from exc

        return self._to_response(job, raw)

    # ------------------------------------------------------------------
    # Candidate context building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_candidate_text(
        profile: CandidateProfile,
        resume_detail: Optional[CandidateResumeDetail],
        skills: set[str],
    ) -> str:
        lines: List[str] = []

        if profile.headline:
            lines.append(f"Headline: {profile.headline}")
        if profile.summary:
            lines.append(f"Summary: {profile.summary}")
        if profile.total_experience is not None:
            lines.append(f"Total Experience: {profile.total_experience} years")
        if profile.current_company:
            lines.append(f"Current Company/Role: {profile.current_company}")
        if profile.experience_level:
            lines.append(f"Experience Level: {profile.experience_level}")
        if profile.current_location:
            lines.append(f"Current Location: {profile.current_location}")
        if profile.target_roles:
            lines.append(f"Target Roles: {profile.target_roles}")

        if skills:
            lines.append(f"Skills: {', '.join(sorted(skills))}")

        experience_lines = JobMatchService._format_experience_entries(resume_detail)
        if experience_lines:
            lines.append("Experience:")
            lines.extend(f"- {line}" for line in experience_lines)

        education_lines = JobMatchService._format_education_entries(resume_detail)
        if education_lines:
            lines.append("Education:")
            lines.extend(f"- {line}" for line in education_lines)

        text = "\n".join(lines).strip()
        return text or "No profile or resume information available for this candidate."

    @staticmethod
    def _format_experience_entries(
        resume_detail: Optional[CandidateResumeDetail],
    ) -> List[str]:
        if not resume_detail or not resume_detail.experience_json:
            return []
        entries = resume_detail.experience_json.get("experience") or []
        lines: List[str] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or item.get("title") or "").strip()
            company = str(item.get("company") or "").strip()
            header = " at ".join(part for part in (role, company) if part)
            if not header:
                continue

            start = str(item.get("start_date") or "").strip()
            end = "Present" if item.get("currently_working") else str(item.get("end_date") or "").strip()
            dates = " - ".join(part for part in (start, end) if part)

            highlights = str(item.get("key_highlights") or "").strip().replace("\n", " ")

            line = header
            if dates:
                line += f" ({dates})"
            if highlights:
                line += f": {highlights}"
            lines.append(line)
        return lines

    @staticmethod
    def _format_education_entries(
        resume_detail: Optional[CandidateResumeDetail],
    ) -> List[str]:
        if not resume_detail or not resume_detail.education_json:
            return []
        entries = resume_detail.education_json.get("education") or []
        lines: List[str] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            institution = str(item.get("institution") or item.get("school") or "").strip()
            degree = str(item.get("degree") or "").strip()
            field_of_study = str(item.get("field_of_study") or "").strip()
            grad_year = item.get("graduation_year")

            qualification = ", ".join(part for part in (degree, field_of_study) if part)
            line = qualification
            if institution:
                line = f"{line} - {institution}" if line else institution
            if grad_year:
                line += f" ({grad_year})"
            if line:
                lines.append(line)
        return lines

    # ------------------------------------------------------------------
    # Job context building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_job_text(job: Job) -> str:
        lines: List[str] = [f"Job Title: {job.title}"]

        if job.company_name:
            lines.append(f"Company: {job.company_name}")
        if job.employment_type:
            lines.append(f"Employment Type: {job.employment_type}")
        if job.experience_min is not None or job.experience_max is not None:
            lo = job.experience_min if job.experience_min is not None else 0
            hi = job.experience_max if job.experience_max is not None else lo
            lines.append(f"Experience Required: {lo}-{hi} years")
        if job.location:
            lines.append(f"Location: {job.location}")
        if job.work_mode:
            lines.append(f"Work Mode: {job.work_mode}")
        if job.education:
            lines.append(f"Education Requirement: {job.education}")

        job_skills = [s.skill for s in (job.skills or []) if s.skill]
        if job_skills:
            lines.append(f"Required Skills: {', '.join(job_skills)}")

        if job.description:
            lines.append(f"Description: {job.description}")

        if job.responsibilities:
            lines.append("Responsibilities:")
            lines.extend(f"- {item}" for item in job.responsibilities if item)

        if job.requirements:
            lines.append("Requirements:")
            lines.extend(f"- {item}" for item in job.requirements if item)

        return "\n".join(lines).strip()

    # ------------------------------------------------------------------
    # Prompt engineering
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(candidate_text: str, job_text: str) -> tuple[str, str]:
        recommendations = ", ".join(f'"{value}"' for value in HIRING_RECOMMENDATIONS)
        system_prompt = (
            "You are an expert technical recruiter and ATS (Applicant Tracking "
            "System) analyst. You compare a candidate's profile and resume "
            "against a job description and assess their fit.\n\n"
            "You MUST respond with ONLY a single valid JSON object and nothing "
            "else -- no markdown, no code fences, no explanations before or "
            "after the JSON. The JSON object must contain exactly these keys:\n"
            '- "match_score": integer from 0 to 100, the overall compatibility score.\n'
            '- "matching_skills": array of strings, skills the candidate has that the job needs.\n'
            '- "missing_skills": array of strings, skills the job needs that the candidate does not show.\n'
            '- "experience_match_analysis": string, 2-4 sentences analyzing how the '
            "candidate's experience aligns with the job's requirements.\n"
            '- "strengths": array of strings, the candidate\'s strengths relevant to this job.\n'
            '- "weaknesses": array of strings, the candidate\'s gaps relevant to this job.\n'
            f'- "hiring_recommendation": exactly one of {recommendations}.\n'
            '- "improvement_suggestions": array of strings, concrete actions the '
            "candidate could take to improve their fit for this job.\n\n"
            "Base your analysis strictly on the candidate and job information "
            "provided below. If information is missing or unclear, make a "
            "reasonable, conservative assessment instead of inventing facts. "
            "Return valid JSON only, with no trailing commentary."
        )

        user_prompt = (
            "CANDIDATE PROFILE AND RESUME:\n"
            f"{candidate_text}\n\n"
            "JOB DESCRIPTION:\n"
            f"{job_text}\n\n"
            "Analyze the fit between this candidate and this job and respond "
            "with the JSON object described in your instructions."
        )
        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # Response mapping / validation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(job: Job, raw: Dict[str, Any]) -> JobMatchScoreResponse:
        try:
            match_score = float(raw.get("match_score", 0))
        except (TypeError, ValueError):
            match_score = 0.0
        match_score = max(0.0, min(100.0, match_score))

        recommendation = str(raw.get("hiring_recommendation") or "").strip()
        if recommendation not in _VALID_RECOMMENDATIONS:
            recommendation = JobMatchService._recommendation_from_score(match_score)

        analysis = raw.get("experience_match_analysis")
        analysis_text = analysis.strip() if isinstance(analysis, str) else ""

        return JobMatchScoreResponse(
            job_id=job.job_id,
            job_title=job.title,
            match_score=round(match_score, 2),
            matching_skills=_as_str_list(raw.get("matching_skills")),
            missing_skills=_as_str_list(raw.get("missing_skills")),
            experience_match_analysis=analysis_text,
            strengths=_as_str_list(raw.get("strengths")),
            weaknesses=_as_str_list(raw.get("weaknesses")),
            hiring_recommendation=recommendation,
            improvement_suggestions=_as_str_list(raw.get("improvement_suggestions")),
        )

    @staticmethod
    def _recommendation_from_score(score: float) -> str:
        """Deterministic fallback used only if Bedrock omits/mislabels
        `hiring_recommendation`, so the API never returns a value outside
        the documented enum."""
        if score >= 85:
            return "Excellent Fit"
        if score >= 65:
            return "Good Fit"
        if score >= 40:
            return "Moderate Fit"
        return "Low Fit"