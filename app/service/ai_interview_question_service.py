"""AI Interview Question Generator service.

Uses AWS Bedrock (via the shared `AIService`, see `app.service.ai_service`)
to generate a structured, personalized set of 15-20 interview questions
for a job the logged-in candidate has applied to -- covering Technical,
Coding (when applicable), Project-based, Behavioral, and HR categories,
each with a concise sample answer.

This deliberately reuses the *same* Bedrock integration already powering
`JobMatchService` (AI Job Match Score) instead of standing up a second
Bedrock client: `AIService` is constructor-injected here exactly as it is
in `app.service.job_match_service.JobMatchService`, so credentials, model
selection, timeouts, JSON parsing, and error translation all keep living
in one place.

Grounding: questions and sample answers are generated from the job's
title/company/description/skills/responsibilities/requirements *and* the
candidate's own profile + latest resume (skills, experience, education).
The AI prompt explicitly forbids inventing candidate experience or
skills that aren't present in that data, mirroring how `JobMatchService`
grounds its analysis.
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
from app.repository.job_application_repo import JobApplicationRepo
from app.schema.ai_interview_question import (
    MAX_QUESTIONS,
    MIN_QUESTIONS,
    QUESTION_CATEGORIES,
    AIInterviewQuestionsResponse,
    InterviewQuestionItem,
)
from app.service.ai_service import AIService, AIServiceError

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = set(QUESTION_CATEGORIES)
_DEFAULT_CATEGORY = "Technical"


class AIInterviewQuestionService:
    """Orchestrates the AI Interview Question Generator feature.

    `ai_service` is constructor-injected (defaulting to a real
    `AIService`) so callers/tests can supply a fake/mocked implementation
    without monkeypatching module internals -- same pattern as
    `JobMatchService`.
    """

    def __init__(self, ai_service: Optional[AIService] = None) -> None:
        self._ai_service = ai_service or AIService()

    async def generate_interview_questions(
        self,
        session: AsyncSession,
        user_id: UUID,
        job_id: str,
    ) -> Optional[AIInterviewQuestionsResponse]:
        profile = await CandidateJobRecommendationRepo.get_candidate_profile(
            session, user_id
        )
        if not profile:
            return None

        job = await JobApplicationRepo.get_job_with_skills(session, job_id)
        if not job:
            return None

        has_applied = await JobApplicationRepo.application_exists(
            session, profile.candidate_id, job_id
        )
        if not has_applied:
            # Distinct from "not found" -- the job and candidate both
            # exist, the candidate just hasn't earned access to this
            # job's question set yet.
            raise HTTPException(
                status_code=403,
                detail=(
                    "You must apply to this job before generating AI "
                    "interview questions for it."
                ),
            )

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
                max_tokens=4000,
                temperature=0.4,
            )
        except AIServiceError as exc:
            logger.error(
                "AI interview question generation failed for job_id=%s, "
                "candidate_id=%s: %s",
                job_id,
                profile.candidate_id,
                exc,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "AI interview question generation is temporarily "
                    "unavailable. Please try again shortly."
                ),
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
        """Renders only candidate-owned data -- profile fields, skills,
        resume experience/education -- into prompt text. Nothing here is
        fabricated; if a field is missing it's simply omitted, so the AI
        prompt never implies the candidate has experience they haven't
        actually reported."""

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

        experience_lines = AIInterviewQuestionService._format_experience_entries(
            resume_detail
        )
        if experience_lines:
            lines.append("Experience:")
            lines.extend(f"- {line}" for line in experience_lines)

        education_lines = AIInterviewQuestionService._format_education_entries(
            resume_detail
        )
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
        """Renders job-owned fields -- title, company, description,
        skills, responsibilities, requirements -- into prompt text."""

        lines: List[str] = [f"Job Title: {job.title}"]

        if job.company_name:
            lines.append(f"Company: {job.company_name}")
        if job.employment_type:
            lines.append(f"Employment Type: {job.employment_type}")
        if job.experience_min is not None or job.experience_max is not None:
            lo = job.experience_min if job.experience_min is not None else 0
            hi = job.experience_max if job.experience_max is not None else lo
            lines.append(f"Experience Required: {lo}-{hi} years")
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
        categories = ", ".join(f'"{value}"' for value in QUESTION_CATEGORIES)
        system_prompt = (
            "You are an expert interview coach and hiring panel lead. "
            "Given a candidate's profile/resume and a single job's "
            "description, required skills, responsibilities, and "
            "requirements, you design a personalized interview question "
            "set that helps this specific candidate prepare for this "
            "specific job.\n\n"
            "You MUST respond with ONLY a single valid JSON object and "
            "nothing else -- no markdown, no code fences, no explanations "
            "before or after the JSON. The JSON object must contain "
            "exactly one key:\n"
            f'- "questions": array of {MIN_QUESTIONS} to {MAX_QUESTIONS} '
            "question objects, covering a mix of the following "
            f"categories: {categories}. Include \"Coding\" questions only "
            "if the job genuinely requires hands-on coding ability; "
            "otherwise omit that category entirely and distribute its "
            "share across the remaining categories so the total still "
            f"falls between {MIN_QUESTIONS} and {MAX_QUESTIONS}. Cover "
            "every other category with at least one question when the "
            "job and candidate information support it.\n\n"
            "Each question object must contain exactly these keys:\n"
            '- "id": integer, include the question position starting at 1.\n'
            '- "category": exactly one of the categories listed above.\n'
            '- "question": string, the interview question text, tailored '
            "to this job and, where relevant, to the candidate's stated "
            "background. Prefer specific, job- and candidate-aware "
            "questions over generic ones whenever the information "
            "provided supports it.\n"
            '- "sample_answer": string, a concise (2-5 sentence) sample '
            "answer written in the candidate's voice (first person) that "
            "a strong candidate could give.\n\n"
            "Grounding rules (follow strictly):\n"
            "- Base every question on the job information provided below "
            "-- do not invent technologies, responsibilities, or "
            "requirements that are not stated or clearly implied by it.\n"
            "- Personalize questions and sample answers using ONLY the "
            "candidate information provided below. Never invent, assume, "
            "or embellish a candidate skill, employer, project, tool, "
            "achievement, or years of experience that is not stated in "
            "that information.\n"
            "- If the candidate information is sparse or missing for a "
            "given question, write a general, best-practice sample answer "
            "(e.g. a STAR-format outline for behavioral/HR questions) "
            "instead of fabricating candidate-specific details.\n"
            "- If the job information is sparse, generate fewer, more "
            "general questions rather than fabricating specifics, but "
            f"still return at least {MIN_QUESTIONS} questions when "
            "possible.\n"
            "Return valid JSON only, with no trailing commentary."
        )

        user_prompt = (
            "CANDIDATE PROFILE AND RESUME:\n"
            f"{candidate_text}\n\n"
            "JOB INFORMATION:\n"
            f"{job_text}\n\n"
            "Generate the personalized interview question set as the "
            "JSON object described in your instructions, using only the "
            "candidate and job information above."
        )
        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # Response mapping / validation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(job: Job, raw: Dict[str, Any]) -> AIInterviewQuestionsResponse:
        questions = AIInterviewQuestionService._as_question_list(raw.get("questions"))

        return AIInterviewQuestionsResponse(
            job_id=job.job_id,
            job_title=job.title,
            company_name=job.company_name or "",
            questions=questions,
        )

    @staticmethod
    def _as_question_list(value: Any) -> List[InterviewQuestionItem]:
        """Defensively coerce an AI-returned field into a clean list of
        `InterviewQuestionItem`s, since the model's output is untrusted
        input even when prompted for strict JSON. Malformed entries are
        dropped rather than raising, mirroring `JobMatchService`'s
        `_as_str_list` approach so a single bad entry can't 500 the API.
        The result is capped at `MAX_QUESTIONS` and re-numbered
        sequentially from 1, since AI-provided ordering/ids are not
        trusted either."""

        if not isinstance(value, list):
            return []

        cleaned: List[tuple[str, str, str]] = []
        for entry in value:
            if not isinstance(entry, dict):
                continue

            question = entry.get("question")
            question_text = question.strip() if isinstance(question, str) else ""
            if not question_text:
                continue

            sample_answer = entry.get("sample_answer") or entry.get("sampleAnswer")
            sample_answer_text = (
                sample_answer.strip() if isinstance(sample_answer, str) else ""
            )
            if not sample_answer_text:
                # Every question must ship with a sample answer -- an
                # entry missing one is incomplete and dropped rather than
                # surfaced with a blank answer.
                continue

            category = str(entry.get("category") or "").strip()
            if category not in _VALID_CATEGORIES:
                category = _DEFAULT_CATEGORY

            cleaned.append((category, question_text, sample_answer_text))
            if len(cleaned) >= MAX_QUESTIONS:
                break

        return [
            InterviewQuestionItem(
                id=idx,
                category=category,
                question=question_text,
                sample_answer=sample_answer_text,
            )
            for idx, (category, question_text, sample_answer_text) in enumerate(
                cleaned, start=1
            )
        ]
