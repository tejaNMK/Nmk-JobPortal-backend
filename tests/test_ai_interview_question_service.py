from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.service.ai_interview_question_service import AIInterviewQuestionService
from app.service.ai_service import AIServiceError
from app.service.candidate_job_recommendation_engine import CandidateMatchContext


class FakeSession:
    """Placeholder session — every DB call in these tests is mocked at the
    repository layer, so the session object itself is never touched."""


class FakeAIService:
    """Stand-in for `AIService` injected via
    `AIInterviewQuestionService(ai_service=...)` so tests never touch
    boto3/Bedrock."""

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
        work_mode="HYBRID",
        education="B.Tech",
        description="We are looking for a senior backend engineer.",
        responsibilities=["Own core services", "Mentor juniors"],
        requirements=["5+ years experience", "Strong Python skills"],
        skills=[SimpleNamespace(skill="Python"), SimpleNamespace(skill="FastAPI")],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _question(
    category="Technical",
    question="How would you design a scalable FastAPI application?",
    sample_answer="I'd start by profiling the hot paths and leaning on async I/O.",
):
    return {"category": category, "question": question, "sample_answer": sample_answer}


VALID_AI_RESPONSE = {"questions": [_question(category=c) for c in
    ["Technical", "Technical", "Technical", "Coding", "Coding",
     "Project-based", "Project-based", "Project-based",
     "Behavioral", "Behavioral", "Behavioral",
     "HR", "HR", "HR", "HR"]]}


def _patch_repos(profile, job, resume_detail, candidate_context, has_applied=True):
    return patch.multiple(
        "app.service.ai_interview_question_service.CandidateJobRecommendationRepo",
        get_candidate_profile=AsyncMock(return_value=profile),
        get_latest_resume_detail=AsyncMock(return_value=resume_detail),
        build_candidate_match_context=AsyncMock(return_value=candidate_context),
    ), patch.multiple(
        "app.service.ai_interview_question_service.JobApplicationRepo",
        get_job_with_skills=AsyncMock(return_value=job),
        application_exists=AsyncMock(return_value=has_applied),
    )


def test_returns_none_when_candidate_profile_missing():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewQuestionService(ai_service=ai_service)

        repo_patch, job_patch = _patch_repos(None, _job(), _resume_detail(), None)
        with repo_patch, job_patch:
            result = await service.generate_interview_questions(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is None
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_returns_none_when_job_not_found():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewQuestionService(ai_service=ai_service)
        profile = _profile()

        repo_patch, job_patch = _patch_repos(profile, None, _resume_detail(), None)
        with repo_patch, job_patch:
            result = await service.generate_interview_questions(
                FakeSession(), uuid4(), "missing-job"
            )

        assert result is None
        assert ai_service.last_call is None

    asyncio.run(run_test())


def test_raises_403_when_candidate_has_not_applied():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewQuestionService(ai_service=ai_service)
        profile = _profile()
        job = _job()

        repo_patch, job_patch = _patch_repos(
            profile, job, _resume_detail(), None, has_applied=False
        )
        with repo_patch, job_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.generate_interview_questions(
                    FakeSession(), uuid4(), "job-1"
                )

        assert exc_info.value.status_code == 403
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_returns_mapped_response_on_successful_ai_call():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewQuestionService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        resume_detail = _resume_detail()
        context = CandidateMatchContext(skills={"python", "fastapi", "postgresql"})

        repo_patch, job_patch = _patch_repos(profile, job, resume_detail, context)
        with repo_patch, job_patch:
            result = await service.generate_interview_questions(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is not None
        assert result.job_id == "job-1"
        assert result.job_title == "Senior Backend Engineer"
        assert result.company_name == "Globex"

        assert len(result.questions) == 15
        assert result.questions[0].id == 1
        assert result.questions[-1].id == 15
        assert {q.category for q in result.questions} == {
            "Technical", "Coding", "Project-based", "Behavioral", "HR",
        }
        assert all(q.sample_answer for q in result.questions)

        # Prompt should include both candidate + job signal, proving the
        # AI call was grounded in real data rather than being called blind.
        prompt = ai_service.last_call["user_prompt"]
        assert "Senior Backend Engineer" in prompt
        assert "Acme Corp" in prompt
        assert "Python" in prompt
        assert "Own core services" in prompt

    asyncio.run(run_test())


def test_invalid_category_falls_back_to_technical():
    async def run_test():
        response = {"questions": [_question(category="Impossible")]}
        ai_service = FakeAIService(response=response)
        service = AIInterviewQuestionService(ai_service=ai_service)
        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.generate_interview_questions(
                FakeSession(), uuid4(), "job-1"
            )

        assert result.questions[0].category == "Technical"

    asyncio.run(run_test())


def test_malformed_entries_are_dropped_not_raised():
    async def run_test():
        response = {
            "questions": [
                {"category": "Technical", "question": "", "sample_answer": "n/a"},  # empty question dropped
                {"category": "Technical", "question": "Explain dependency injection."},  # missing sample_answer dropped
                "not-a-dict",  # dropped
                _question(category="Behavioral", question="Describe a conflict you resolved."),
            ]
        }
        ai_service = FakeAIService(response=response)
        service = AIInterviewQuestionService(ai_service=ai_service)
        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.generate_interview_questions(
                FakeSession(), uuid4(), "job-1"
            )

        assert len(result.questions) == 1
        assert result.questions[0].id == 1
        assert result.questions[0].question == "Describe a conflict you resolved."

    asyncio.run(run_test())


def test_question_list_is_capped_at_max_questions():
    async def run_test():
        response = {"questions": [_question(question=f"Question {i}") for i in range(30)]}
        ai_service = FakeAIService(response=response)
        service = AIInterviewQuestionService(ai_service=ai_service)
        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.generate_interview_questions(
                FakeSession(), uuid4(), "job-1"
            )

        assert len(result.questions) == 20
        assert result.questions[-1].id == 20

    asyncio.run(run_test())


def test_ai_service_error_raises_http_503():
    async def run_test():
        ai_service = FakeAIService(error=AIServiceError("Bedrock is down"))
        service = AIInterviewQuestionService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.generate_interview_questions(
                    FakeSession(), uuid4(), "job-1"
                )

        assert exc_info.value.status_code == 503

    asyncio.run(run_test())


def test_works_without_a_resume_on_file():
    """A candidate with a profile but no uploaded resume should still get
    a question set, personalized from profile fields only."""

    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewQuestionService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, None, context)
        with repo_patch, job_patch:
            result = await service.generate_interview_questions(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is not None
        assert len(result.questions) == 15

    asyncio.run(run_test())


def test_response_serializes_with_camelcase_aliases():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = AIInterviewQuestionService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.generate_interview_questions(
                FakeSession(), uuid4(), "job-1"
            )

        dumped = result.model_dump(by_alias=True)
        assert dumped["jobTitle"] == "Senior Backend Engineer"
        assert dumped["companyName"] == "Globex"
        assert dumped["questions"][0]["sampleAnswer"]

    asyncio.run(run_test())