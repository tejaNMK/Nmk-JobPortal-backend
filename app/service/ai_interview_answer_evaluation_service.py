"""AI Interview Answer Evaluation service.

Uses AWS Bedrock (via the shared `AIService`, see `app.service.ai_service`)
to evaluate a candidate's own answer to a single interview question, for a
single job the candidate has applied to -- returning an overall 0-100
score, three sub-scores (Technical Accuracy, Relevance, Clarity),
strengths, areas for improvement, detailed feedback, and a suggested
improved answer.

This deliberately reuses -- and does not duplicate -- the existing AI
Interview Question Generator's data access and prompt-text building:
    - Candidate/job data access reuses `CandidateJobRecommendationRepo`
      and `JobApplicationRepo`, exactly as `AIInterviewQuestionService`
      already does (including the same `get_job_with_skills` /
      `application_exists` "has this candidate applied?" gate).
    - Candidate/job prompt-text rendering reuses
      `AIInterviewQuestionService._build_candidate_text` /
      `._build_job_text` directly rather than re-implementing the same
      formatting.
    - The Bedrock call goes through the same shared `AIService` used by
      every other candidate-side AI feature (`JobMatchService`,
      `AIInterviewQuestionService`, `AICoverLetterService`, ...),
      including its JSON parsing/repair and error handling.

The existing Interview Question Generator API/service/schema
(`ai_interview_question.py` controller route, `AIInterviewQuestionService`,
`app/schema/ai_interview_question.py`) is not modified.

Fabrication safety
-------------------
Same hard requirement as `AIInterviewQuestionService`'s sample answers:
the evaluation -- and especially `suggested_improved_answer` -- must never
credit the candidate with an employer, project, tool, metric, skill, or
years of experience they haven't actually reported. The system prompt
enforces this explicitly and temperature is kept low (0.2) for
faithfulness over creativity.
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
from app.repository.job_application_repo import JobApplicationRepo
from app.schema.ai_interview_answer_evaluation import (
    AIInterviewAnswerEvaluationRequest,
    AIInterviewAnswerEvaluationResponse,
)
from app.service.ai_interview_question_service import AIInterviewQuestionService
from app.service.ai_service import AIService, AIServiceError, ai_error_status_code

logger = logging.getLogger(__name__)

_MAX_OUTPUT_TOKENS = 1800
_TEMPERATURE = 0.2


def _as_score(value: Any) -> float:
    """Defensively coerce an AI-returned score into a float clamped to
    [0, 100] -- mirrors the score-clamping already used by
    `JobMatchService._to_response` / `ApplicationReadinessService`."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(100.0, score))


def _as_str_list(value: Any) -> List[str]:
    """Defensively coerce an AI-returned field into a clean list of
    non-empty strings -- mirrors `job_match_service._as_str_list` so
    every AI feature in this codebase sanitizes AI list output
    identically."""
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


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


class AIInterviewAnswerEvaluationService:
    """Orchestrates the AI Interview Answer Evaluation feature.

    `ai_service` is constructor-injected (defaulting to a real
    `AIService`), matching every other AI-backed service in this
    codebase, so tests/callers can supply a fake implementation without
    touching boto3/Bedrock.
    """

    def __init__(self, ai_service: Optional[AIService] = None) -> None:
        self._ai_service = ai_service or AIService()

    async def evaluate_answer(
        self,
        session: AsyncSession,
        user_id: UUID,
        request: AIInterviewAnswerEvaluationRequest,
    ) -> Optional[AIInterviewAnswerEvaluationResponse]:
        """Evaluate `request.answer` to `request.question` for
        `request.job_id`, for the logged-in candidate.

        Returns `None` if the candidate profile or the job isn't found
        (mapped to 404 by the controller, mirroring
        `AIInterviewQuestionService`). Raises `HTTPException(403)` if the
        candidate hasn't applied to this job, and
        `HTTPException(502/503)` if Bedrock fails.
        """

        profile = await CandidateJobRecommendationRepo.get_candidate_profile(
            session, user_id
        )
        if not profile:
            return None

        job = await JobApplicationRepo.get_job_with_skills(session, request.job_id)
        if not job:
            return None

        has_applied = await JobApplicationRepo.application_exists(
            session, profile.candidate_id, request.job_id
        )
        if not has_applied:
            # Same gate as AIInterviewQuestionService.generate_interview_questions:
            # distinct from "not found" -- the job and candidate both exist,
            # the candidate just hasn't earned access to answer evaluation
            # for this job yet.
            raise HTTPException(
                status_code=403,
                detail=(
                    "You must apply to this job before getting AI interview "
                    "answer evaluations for it."
                ),
            )

        resume_detail = await CandidateJobRecommendationRepo.get_latest_resume_detail(
            session, profile.candidate_id
        )
        candidate_context = await CandidateJobRecommendationRepo.build_candidate_match_context(
            session, profile
        )

        # Reuse AIInterviewQuestionService's prompt-text builders instead
        # of re-formatting candidate/job data.
        candidate_text = AIInterviewQuestionService._build_candidate_text(
            profile, resume_detail, candidate_context.skills
        )
        job_text = AIInterviewQuestionService._build_job_text(job)

        system_prompt, user_prompt = self._build_prompt(
            candidate_text,
            job_text,
            question=request.question.strip(),
            answer=request.answer.strip(),
        )

        try:
            raw = self._ai_service.invoke_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=_MAX_OUTPUT_TOKENS,
                temperature=_TEMPERATURE,
            )
        except AIServiceError as exc:
            logger.error(
                "AI interview answer evaluation failed for job_id=%s, "
                "candidate_id=%s: %s",
                request.job_id,
                profile.candidate_id,
                exc,
            )
            raise HTTPException(
                status_code=ai_error_status_code(exc),
                detail=(
                    "AI interview answer evaluation is temporarily "
                    "unavailable. Please try again shortly."
                ),
            ) from exc

        return self._to_response(job, request.question.strip(), raw)

    # ------------------------------------------------------------------
    # Prompt engineering
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        candidate_text: str,
        job_text: str,
        *,
        question: str,
        answer: str,
    ) -> tuple[str, str]:
        system_prompt = (
            "You are an expert interview coach and hiring panel lead. "
            "Given a candidate's profile/resume, a single job's "
            "description and requirements, one interview question for "
            "that job, and the candidate's own answer to that question, "
            "you evaluate how good that answer is for this specific job "
            "and question.\n\n"
            "You MUST respond with ONLY a single valid JSON object and "
            "nothing else -- no markdown, no code fences, no explanations "
            "before or after the JSON. The JSON object must contain "
            "exactly these keys:\n"
            '- "overall_score": integer from 0 to 100, your holistic '
            "assessment of the answer's quality for this question and "
            "job.\n"
            '- "technical_accuracy": integer from 0 to 100, how '
            "technically correct and sound the answer is. If the "
            "question is not technical in nature, assess factual/"
            "professional correctness instead and still return a "
            "reasonable score rather than 0.\n"
            '- "relevance": integer from 0 to 100, how directly the '
            "answer addresses the actual question asked and how well it "
            "connects to what this specific job needs.\n"
            '- "clarity": integer from 0 to 100, how clear, well-'
            "structured, and easy to follow the answer is.\n"
            '- "strengths": array of strings, what the answer does '
            "well.\n"
            '- "areas_for_improvement": array of strings, specific '
            "weaknesses or gaps in the answer (content, structure, "
            "depth, or relevance).\n"
            '- "detailed_feedback": string, 2-5 sentences of concrete, '
            "constructive feedback explaining the scores above.\n"
            '- "suggested_improved_answer": string, a stronger version '
            "of the candidate's answer to the same question.\n\n"
            "Grounding rules (follow strictly -- these are hard "
            "requirements):\n"
            "- Evaluate the answer strictly against the job information "
            "and the exact question provided below -- do not evaluate it "
            "against a different or generic version of the question.\n"
            "- When writing \"suggested_improved_answer\", use ONLY "
            "experience, skills, projects, employers, tools, and "
            "achievements that are explicitly present in the CANDIDATE "
            "PROFILE AND RESUME section below, or that the candidate "
            "themselves already mentioned in their own answer. NEVER "
            "invent, assume, or embellish a candidate skill, employer, "
            "project, tool, achievement, metric, or years of experience "
            "that is not stated in that information -- if the candidate's "
            "real background is too thin to fully answer the question, "
            "write a stronger answer using general best practice (e.g. a "
            "STAR-format outline) around what they actually have, rather "
            "than fabricating specifics.\n"
            "- \"strengths\", \"areas_for_improvement\", and "
            "\"detailed_feedback\" must be based only on what the "
            "candidate actually wrote in their answer and on the real "
            "candidate/job information provided -- do not credit or "
            "penalize the candidate for experience they did not "
            "mention.\n"
            "- If the candidate's answer is empty of substance, off-"
            "topic, or clearly does not attempt to answer the question, "
            "score it low across all four scores and say so plainly in "
            "\"detailed_feedback\" rather than inventing merit that isn't "
            "there.\n"
            "Return valid JSON only, with no trailing commentary."
        )

        user_prompt = (
            "CANDIDATE PROFILE AND RESUME:\n"
            f"{candidate_text}\n\n"
            "JOB INFORMATION:\n"
            f"{job_text}\n\n"
            "INTERVIEW QUESTION:\n"
            f"{question}\n\n"
            "CANDIDATE'S ANSWER:\n"
            f"{answer}\n\n"
            "Evaluate this answer and respond with the JSON object "
            "described in your instructions."
        )
        return system_prompt, user_prompt

    # ------------------------------------------------------------------
    # Response mapping / validation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(
        job: Job,
        question: str,
        raw: Dict[str, Any],
    ) -> AIInterviewAnswerEvaluationResponse:
        return AIInterviewAnswerEvaluationResponse(
            job_id=job.job_id,
            job_title=job.title or "",
            company_name=job.company_name or "",
            question=question,
            overall_score=round(_as_score(raw.get("overall_score")), 2),
            technical_accuracy=round(_as_score(raw.get("technical_accuracy")), 2),
            relevance=round(_as_score(raw.get("relevance")), 2),
            clarity=round(_as_score(raw.get("clarity")), 2),
            strengths=_as_str_list(raw.get("strengths")),
            areas_for_improvement=_as_str_list(raw.get("areas_for_improvement")),
            detailed_feedback=_as_text(raw.get("detailed_feedback")),
            suggested_improved_answer=_as_text(raw.get("suggested_improved_answer")),
        )