"""AI Cover Letter Generator service.

Uses AWS Bedrock (via the existing `AIService`, the same reusable Bedrock
wrapper `AIProfileWriterService` / `AITextAssistService` / `JobMatchService`
already rely on) to draft a cover letter for the logged-in candidate,
tailored to one specific job posting.

Data access mirrors `AIProfileWriterService`: candidate profile + latest
resume detail are loaded via the same `CandidateJobRecommendationRepo`
helpers (`get_candidate_profile`, `get_latest_resume_detail`,
`build_candidate_match_context`), and the target job is loaded via the
existing `JobRepository.get_job_by_id`, so this feature adds no new query
patterns to the codebase.

Fabrication safety
-------------------
Same hard requirement as the AI Profile Writer: never invent employers,
titles, dates, metrics, or skills. The system prompt explicitly restricts
the model to the candidate facts and job facts supplied in the prompt, and
temperature is kept low (0.3) for faithfulness over creativity. Unlike
Headline/About there is no structured ground truth to splice back in
afterwards (a cover letter is one prose document, not discrete fields), so
this feature leans entirely on prompt engineering plus the same low
temperature already used for the free-text `AITextAssistService`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.employer_model.job import Job
from app.repository.authentication.users import UsersRepository
from app.repository.candidate_repository.candidate_job_recommendation_repo import (
    CandidateJobRecommendationRepo,
)
from app.repository.employer_repository.job_repo import JobRepository
from app.schema.ai_cover_letter import (
    AICoverLetterLength,
    AICoverLetterRequest,
    AICoverLetterResponse,
    AICoverLetterTone,
)
from app.service.ai_service import AIService, AIServiceError, ai_error_status_code

logger = logging.getLogger(__name__)

AI_COVER_LETTER_FEATURE_KEY = "candidate_ai_cover_letter"
AI_COVER_LETTER_PROMPT_VERSION = "v1"

_MAX_OUTPUT_TOKENS = 1400
_TEMPERATURE = 0.3
_MAX_EXPERIENCE_ENTRIES = 6  # keeps prompt size bounded; most relevant/recent roles first

_TONE_GUIDANCE: Dict[AICoverLetterTone, str] = {
    AICoverLetterTone.PROFESSIONAL: "formal, polished, and business-appropriate",
    AICoverLetterTone.CONFIDENT: "confident and assertive, emphasizing impact and ownership",
    AICoverLetterTone.FRIENDLY: "warm and approachable while remaining professional",
    AICoverLetterTone.CONCISE: "crisp and to-the-point, no filler words",
    AICoverLetterTone.ENTHUSIASTIC: "energetic and genuinely excited about the role and company",
}

_LENGTH_GUIDANCE: Dict[AICoverLetterLength, str] = {
    AICoverLetterLength.SHORT: "brief -- about 3 short paragraphs (roughly 150-200 words total)",
    AICoverLetterLength.MEDIUM: "standard cover letter length -- about 4 paragraphs (roughly 250-350 words total)",
    AICoverLetterLength.LONG: "detailed -- about 5 paragraphs (roughly 350-450 words total)",
}


class AICoverLetterService:
    """Orchestrates the AI Cover Letter Generator feature.

    `ai_service` is constructor-injected (defaulting to a real
    `AIService`), matching every other AI-backed service in this codebase,
    so tests/callers can supply a fake implementation without touching
    boto3/Bedrock.
    """

    def __init__(self, ai_service: Optional[AIService] = None) -> None:
        self._ai_service = ai_service or AIService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        session: AsyncSession,
        user_id: UUID,
        request: AICoverLetterRequest,
    ) -> Optional[AICoverLetterResponse]:
        """Generate (or revise, if `request.existing_text` is set) a cover
        letter for the logged-in candidate, tailored to `request.job_id`.

        Returns `None` if the candidate profile isn't found. Raises
        `HTTPException(404)` if the job isn't found and
        `HTTPException(503/502/...)` if Bedrock fails -- mirroring
        `AIProfileWriterService`'s error handling.
        """

        profile = await CandidateJobRecommendationRepo.get_candidate_profile(session, user_id)
        if not profile:
            return None

        job = await JobRepository.get_job_by_id(session=session, job_id=request.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        user = await UsersRepository.find_by_user_id(session, str(user_id))

        resume_detail = await CandidateJobRecommendationRepo.get_latest_resume_detail(
            session, profile.candidate_id
        )
        candidate_context = await CandidateJobRecommendationRepo.build_candidate_match_context(
            session, profile
        )
        experience_entries = self._extract_experience_entries(resume_detail)

        candidate_text = self._build_candidate_text(
            user, profile, candidate_context.skills, experience_entries
        )
        job_text = self._build_job_text(job)

        tone = request.tone or AICoverLetterTone.PROFESSIONAL
        length = request.length or AICoverLetterLength.MEDIUM

        system_prompt, user_prompt = self._build_prompt(
            candidate_text,
            job_text,
            tone=tone,
            length=length,
            additional_notes=request.additional_notes,
            existing_text=request.existing_text,
        )

        try:
            result = await self._ai_service.ainvoke_with_usage(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=_MAX_OUTPUT_TOKENS,
                temperature=_TEMPERATURE,
                feature=AI_COVER_LETTER_FEATURE_KEY,
                prompt_version=AI_COVER_LETTER_PROMPT_VERSION,
            )
        except AIServiceError as exc:
            logger.error(
                "AI cover letter generation failed for candidate_id=%s, job_id=%s: %s",
                profile.candidate_id,
                request.job_id,
                exc,
            )
            raise HTTPException(
                status_code=ai_error_status_code(exc),
                detail="AI cover letter generator is temporarily unavailable. Please try again shortly.",
            ) from exc

        cover_letter_text = self._clean_output(result.content)
        if not cover_letter_text:
            logger.warning(
                "AI cover letter generation produced no usable output for "
                "candidate_id=%s, job_id=%s.",
                profile.candidate_id,
                request.job_id,
            )
            raise HTTPException(
                status_code=502,
                detail="The AI cover letter writer had trouble responding. Please try again.",
            )

        return AICoverLetterResponse(
            cover_letter_text=cover_letter_text,
            job_id=job.job_id,
            job_title=job.title or "",
            company_name=job.company_name,
        )

    # ------------------------------------------------------------------
    # Candidate / job context building
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_experience_entries(resume_detail) -> List[Dict[str, Any]]:
        """Pull structured experience entries straight from the
        candidate's own resume JSON -- mirrors
        `AIProfileWriterService._extract_experience_entries`, most
        recent/relevant entries first, bounded so the prompt stays a
        reasonable size."""

        if not resume_detail or not getattr(resume_detail, "experience_json", None):
            return []
        entries = resume_detail.experience_json.get("experience") or []

        cleaned: List[Dict[str, Any]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or item.get("title") or "").strip()
            company = str(item.get("company") or "").strip()
            if not role and not company:
                continue
            cleaned.append(
                {
                    "role": role or "Team Member",
                    "company": company or "Not specified",
                    "start_date": str(item.get("start_date") or "").strip(),
                    "end_date": "Present" if item.get("currently_working") else str(item.get("end_date") or "").strip(),
                    "key_highlights": str(item.get("key_highlights") or "").strip(),
                }
            )
        return cleaned[:_MAX_EXPERIENCE_ENTRIES]

    @staticmethod
    def _build_candidate_text(
        user,
        profile,
        skills: set,
        experience_entries: List[Dict[str, Any]],
    ) -> str:
        lines: List[str] = []

        full_name = " ".join(
            part
            for part in (
                getattr(user, "first_name", None),
                getattr(user, "last_name", None),
            )
            if part
        ).strip()
        if full_name:
            lines.append(f"Candidate Name: {full_name}")
        if profile.headline:
            lines.append(f"Current Headline: {profile.headline}")
        if profile.summary:
            lines.append(f"Professional Summary: {profile.summary}")
        if profile.total_experience is not None:
            lines.append(f"Total Experience: {profile.total_experience} years")
        if profile.current_company:
            lines.append(f"Current Company/Role: {profile.current_company}")
        if profile.experience_level:
            lines.append(f"Experience Level: {profile.experience_level}")

        if skills:
            lines.append(f"Skills: {', '.join(sorted(skills))}")

        if experience_entries:
            lines.append("Work Experience (do not add, remove, or invent entries):")
            for idx, entry in enumerate(experience_entries, start=1):
                dates = " - ".join(part for part in (entry["start_date"], entry["end_date"]) if part)
                header = f"{idx}. {entry['role']} at {entry['company']}"
                if dates:
                    header += f" ({dates})"
                lines.append(header)
                if entry["key_highlights"]:
                    lines.append(f"   Highlights: {entry['key_highlights']}")

        text = "\n".join(lines).strip()
        return text or "No profile or resume information available for this candidate."

    @staticmethod
    def _build_job_text(job: Job) -> str:
        lines: List[str] = [f"Job Title: {job.title or 'Not specified'}"]
        if job.company_name:
            lines.append(f"Company: {job.company_name}")
        if job.location:
            lines.append(f"Location: {job.location}")
        if job.employment_type:
            lines.append(f"Employment Type: {job.employment_type}")
        if job.work_mode:
            lines.append(f"Work Mode: {job.work_mode}")
        if job.description:
            lines.append(f"Job Description: {job.description}")
        if job.responsibilities:
            lines.append("Responsibilities: " + "; ".join(job.responsibilities))
        if job.requirements:
            lines.append("Requirements: " + "; ".join(job.requirements))
        skills = {s.skill for s in (job.skills or []) if getattr(s, "skill", None)}
        if skills:
            lines.append(f"Required Skills: {', '.join(sorted(skills))}")
        return "\n".join(lines).strip()

    # ------------------------------------------------------------------
    # Prompt engineering
    # ------------------------------------------------------------------

    @classmethod
    def _build_prompt(
        cls,
        candidate_text: str,
        job_text: str,
        *,
        tone: AICoverLetterTone,
        length: AICoverLetterLength,
        additional_notes: Optional[str],
        existing_text: Optional[str],
    ) -> tuple[str, str]:
        tone_guidance = _TONE_GUIDANCE[tone]
        length_guidance = _LENGTH_GUIDANCE[length]

        if existing_text and existing_text.strip():
            task = (
                "The candidate already has a draft cover letter for this job "
                "(see 'CANDIDATE'S CURRENT DRAFT' below). Revise it to match "
                "the requested tone/length while keeping every fact from the "
                "draft -- do not turn it into a completely different letter, "
                "and do not add any new employer, title, date, metric, or "
                "skill that isn't already in the draft or the candidate "
                "context below."
            )
        else:
            task = (
                "Draft a brand-new cover letter for the candidate, tailored to "
                "the job below, using ONLY the candidate context provided -- "
                "never invent an employer, title, date, metric, or skill that "
                "isn't already present in that context."
            )

        system_prompt = (
            "You are an expert career coach and professional cover letter "
            "writer. You write a single, complete cover letter for ONE "
            "specific job application, addressed to that company, using "
            "only the facts given to you about the candidate and the job. "
            "You NEVER invent employers, job titles, dates, metrics, "
            "certifications, or skills that are not already present in the "
            "candidate context you were given, and you never fabricate "
            "details about the hiring company beyond what's in the job "
            "posting.\n\n"
            f"TASK: {task}\n\n"
            f"TONE: Write in a tone that is {tone_guidance}.\n"
            f"LENGTH: The letter should be {length_guidance}.\n\n"
            "STRUCTURE: A clear opening that names the role and company and "
            "why the candidate is interested, 1-2 body paragraphs that "
            "connect the candidate's real experience and skills to the "
            "job's actual requirements, and a closing paragraph with a call "
            "to action and a professional sign-off using the candidate's "
            "name if given (otherwise a generic closing like 'Sincerely,').\n\n"
            "FORMAT: Plain text only -- no markdown, no bullet points, no "
            "placeholders like '[Company Address]' or '[Date]', no "
            "commentary about what you did. Respond with ONLY the finished "
            "cover letter text and nothing else."
        )

        user_prompt_parts = ["CANDIDATE CONTEXT:", candidate_text, "", "JOB POSTING:", job_text]
        if additional_notes and additional_notes.strip():
            user_prompt_parts += ["", f"CANDIDATE'S ADDITIONAL NOTES (steer emphasis only, not new facts): {additional_notes.strip()}"]
        if existing_text and existing_text.strip():
            user_prompt_parts += ["", "CANDIDATE'S CURRENT DRAFT:", existing_text.strip()]
        user_prompt = "\n".join(user_prompt_parts)

        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # Output cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_output(raw: str) -> str:
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
            cleaned = cleaned[1:-1].strip()
        return cleaned