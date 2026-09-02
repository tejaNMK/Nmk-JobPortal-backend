from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schema.ai_interview_answer_evaluation import AIInterviewAnswerEvaluationRequest
from app.service.ai_interview_answer_evaluation_service import (
    AIInterviewAnswerEvaluationService,
)
from app.service.ai_service import AIServiceError
from app.service.candidate_job_recommendation_engine import CandidateMatchContext


class FakeSession:
    """Placeholder session — every DB call in these tests is mocked at the
    repository layer, so the session object itself is never touched."""


class FakeAIService:
    """Stand-in for `AIService` injected via
    `AIInterviewAnswerEvaluationService(ai_service=...)`, so tests never
    touch boto3/Bedrock -- same pattern as
    `tests/test_ai_interview_question_service.py`."""

    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self._response = response
        self._error = error
        self.last_call = None

    def invoke_json(self, **kwargs):
        self.last_call = kwargs
        if self._error:
            raise self._error
        return self._response


def _profile(**overrides) -> SimpleNamespace:
    base = dict(
        candidate_id="candidate-1",
        user_id=uuid4(),
        headline="Senior Backend Engineer",
        summary="6 years building backend systems.",
        total_experience=6,
        current_company="Acme Corp",
        experience_level="Senior",
        current_location="Bengaluru",
        target_roles="Backend Engineer, Platform Engineer",
        skills_summary="Python, FastAPI",
        profile_completion_pct=70,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _resume_detail(**overrides) -> SimpleNamespace:
    base = dict(
        experience_json={
            "experience": [
                {
                    "role": "Backend Engineer",
                    "company": "Acme Corp",
                    "start_date": "2020-01",
                    "end_date": None,
                    "currently_working": True,
                    "key_highlights": "Built the core API platform.",
                }
            ]
        },
        education_json={
            "education": [
                {
                    "institution": "State University",
                    "degree": "B.Tech",
                    "field_of_study": "Computer Science",
                    "graduation_year": 2018,
                }
            ]
        },
        skills_json={"skills": ["Python", "FastAPI", "PostgreSQL"]},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _job(**overrides) -> SimpleNamespace:
    base = dict(
        job_id="job-1",
        title="Senior Backend Engineer",
        company_name="Globex",
        employment_type="FULL_TIME",
        experience_min=5,
        experience_max=8,
        location="Bengaluru",
        work_mode="HYBRID",
        education="B.Tech",
        description="We are looking for a senior backend engineer.",
        responsibilities=["Own core services", "Mentor juniors"],
        requirements=["5+ years experience", "Strong Python skills"],
        skills=[SimpleNamespace(skill="Python"), SimpleNamespace(skill="Kubernetes")],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _request(**overrides) -> AIInterviewAnswerEvaluationRequest:
    base = dict(
        job_id="job-1",
        question="How would you design this role's core service to scale?",
        answer="I'd profile the hot paths, then apply async I/O and connection pooling.",
    )
    base.update(overrides)
    return AIInterviewAnswerEvaluationRequest(**base)


VALID_AI_RESPONSE = {
    "overall_score": 72,
    "technical_accuracy": 75,
    "relevance": 80,
    "clarity": 65,
    "strengths": ["Correctly identifies caching and async I/O as levers"],
    "areas_for_improvement": ["Answer stays generic rather than giving a concrete example"],
    "detailed_feedback": "Solid awareness of scaling concepts but stays generic.",
    "suggested_improved_answer": "I'd start by profiling the hot paths in the service...",
}


def _patch_repos(profile, job, resume_detail, candidate_context, has_applied=True):
    return (
        patch.multiple(
            "app.service.ai_interview_answer_evaluation_service.CandidateJobRecommendationRepo",
            get_candidate_profile=AsyncMock(return_value=profile),
            get_latest_resume_detail=AsyncMock(return_value=resume_detail),
            build_candidate_match_context=AsyncMock(return_value=candidate_context),
        ),
        patch.multiple(
            "app.service.ai_interview_answer_evaluation_service.JobApplicationRepo",
            get_job_with_skills=AsyncMock(return_value=job),
            application_exists=AsyncMock(return_value=has_applied),
        ),
    )


def _full_context() -> CandidateMatchContext:
    return CandidateMatchContext(
        skills={"python", "fastapi", "postgresql"},
        total_experience_years=6,
        headline="Senior Backend Engineer",
        current_designation="Acme Corp",
        current_location="Bengaluru",
        profile_completion_pct=70,
    )


def test_returns_none_when_candidate_profile_missing():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewAnswerEvaluationService(ai_service=ai_service)

        repo_patch, app_patch = _patch_repos(None, _job(), _resume_detail(), None)
        with repo_patch, app_patch:
            result = await service.evaluate_answer(FakeSession(), uuid4(), _request())

        assert result is None
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_returns_none_when_job_not_found():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewAnswerEvaluationService(ai_service=ai_service)
        profile = _profile()

        repo_patch, app_patch = _patch_repos(profile, None, _resume_detail(), None)
        with repo_patch, app_patch:
            result = await service.evaluate_answer(
                FakeSession(), uuid4(), _request(job_id="missing-job")
            )

        assert result is None
        assert ai_service.last_call is None

    asyncio.run(run_test())


def test_raises_403_when_candidate_has_not_applied():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewAnswerEvaluationService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, app_patch = _patch_repos(
            profile, job, _resume_detail(), context, has_applied=False
        )
        with repo_patch, app_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.evaluate_answer(FakeSession(), uuid4(), _request())

        assert exc_info.value.status_code == 403
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_returns_mapped_response_on_successful_ai_call():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewAnswerEvaluationService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        resume_detail = _resume_detail()
        context = _full_context()

        repo_patch, app_patch = _patch_repos(profile, job, resume_detail, context)
        with repo_patch, app_patch:
            result = await service.evaluate_answer(FakeSession(), uuid4(), _request())

        assert result is not None
        assert result.job_id == "job-1"
        assert result.job_title == "Senior Backend Engineer"
        assert result.company_name == "Globex"
        assert result.question == "How would you design this role's core service to scale?"

        assert result.overall_score == 72.0
        assert result.technical_accuracy == 75.0
        assert result.relevance == 80.0
        assert result.clarity == 65.0
        assert result.strengths == ["Correctly identifies caching and async I/O as levers"]
        assert result.areas_for_improvement == [
            "Answer stays generic rather than giving a concrete example"
        ]
        assert "generic" in result.detailed_feedback
        assert "profiling the hot paths" in result.suggested_improved_answer

        # Prompt should be grounded in real candidate + job + Q&A data.
        prompt = ai_service.last_call["user_prompt"]
        assert "Senior Backend Engineer" in prompt
        assert "Python" in prompt
        assert "Acme Corp" in prompt
        assert "How would you design this role's core service to scale?" in prompt
        assert "I'd profile the hot paths" in prompt

    asyncio.run(run_test())


def test_out_of_range_ai_scores_are_clamped():
    async def run_test():
        response = dict(VALID_AI_RESPONSE)
        response["overall_score"] = 145
        response["clarity"] = -20

        ai_service = FakeAIService(response=response)
        service = AIInterviewAnswerEvaluationService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, app_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, app_patch:
            result = await service.evaluate_answer(FakeSession(), uuid4(), _request())

        assert result.overall_score == 100.0
        assert result.clarity == 0.0

    asyncio.run(run_test())


def test_malformed_list_fields_are_sanitized_not_raised():
    async def run_test():
        response = dict(VALID_AI_RESPONSE)
        response["strengths"] = "Good use of caching"  # not a list
        response["areas_for_improvement"] = [None, "", "  Too generic  ", {"nested": "dict"}]

        ai_service = FakeAIService(response=response)
        service = AIInterviewAnswerEvaluationService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, app_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, app_patch:
            result = await service.evaluate_answer(FakeSession(), uuid4(), _request())

        assert result.strengths == []  # non-list input -> empty, not a crash
        assert result.areas_for_improvement == ["Too generic"]

    asyncio.run(run_test())


def test_ai_service_error_raises_http_error():
    async def run_test():
        ai_service = FakeAIService(error=AIServiceError("Bedrock is down"))
        service = AIInterviewAnswerEvaluationService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, app_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, app_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.evaluate_answer(FakeSession(), uuid4(), _request())

        assert exc_info.value.status_code in (502, 503)

    asyncio.run(run_test())


def test_works_without_a_resume_on_file():
    """A candidate with a profile but no uploaded resume should still get
    an evaluation, using profile fields only."""

    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewAnswerEvaluationService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, app_patch = _patch_repos(profile, job, None, context)
        with repo_patch, app_patch:
            result = await service.evaluate_answer(FakeSession(), uuid4(), _request())

        assert result is not None
        assert result.overall_score == 72.0

    asyncio.run(run_test())


def test_request_rejects_blank_fields():
    with pytest.raises(ValidationError):
        AIInterviewAnswerEvaluationRequest(job_id="  ", question="Q?", answer="A")

    with pytest.raises(ValidationError):
        AIInterviewAnswerEvaluationRequest(job_id="job-1", question="   ", answer="A")

    with pytest.raises(ValidationError):
        AIInterviewAnswerEvaluationRequest(job_id="job-1", question="Q?", answer="   ")


def test_request_rejects_oversized_answer():
    with pytest.raises(ValidationError):
        AIInterviewAnswerEvaluationRequest(
            job_id="job-1", question="Q?", answer="x" * 8001
        )