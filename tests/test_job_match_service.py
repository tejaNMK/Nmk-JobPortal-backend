from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.service.ai_service import AIServiceError
from app.service.candidate_job_recommendation_engine import CandidateMatchContext
from app.service.job_match_service import JobMatchService


class FakeSession:
    """Placeholder session — every DB call in these tests is mocked at the
    repository layer, so the session object itself is never touched."""


class FakeAIService:
    """Stand-in for `AIService` injected via `JobMatchService(ai_service=...)`
    so tests never touch boto3/Bedrock."""

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


VALID_AI_RESPONSE = {
    "match_score": 82,
    "matching_skills": ["Python", "FastAPI"],
    "missing_skills": ["Kubernetes"],
    "experience_match_analysis": "Strong alignment with the required experience range.",
    "strengths": ["Deep backend expertise"],
    "weaknesses": ["No container orchestration experience listed"],
    "hiring_recommendation": "Good Fit",
    "improvement_suggestions": ["Add Kubernetes exposure to the resume"],
}


def _patch_repos(profile, job, resume_detail, candidate_context):
    return patch.multiple(
        "app.service.job_match_service.CandidateJobRecommendationRepo",
        get_candidate_profile=AsyncMock(return_value=profile),
        get_latest_resume_detail=AsyncMock(return_value=resume_detail),
        build_candidate_match_context=AsyncMock(return_value=candidate_context),
    ), patch(
        "app.service.job_match_service.CandidateJobSearchRepo.get_job_details",
        new=AsyncMock(return_value=job),
    )


def test_returns_none_when_candidate_profile_missing():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = JobMatchService(ai_service=ai_service)

        repo_patch, job_patch = _patch_repos(None, _job(), _resume_detail(), None)
        with repo_patch, job_patch:
            result = await service.get_job_match_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is None
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_returns_none_when_job_not_found():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = JobMatchService(ai_service=ai_service)
        profile = _profile()

        repo_patch, job_patch = _patch_repos(profile, None, _resume_detail(), None)
        with repo_patch, job_patch:
            result = await service.get_job_match_score(
                FakeSession(), uuid4(), "missing-job"
            )

        assert result is None
        assert ai_service.last_call is None

    asyncio.run(run_test())


def test_returns_mapped_response_on_successful_ai_call():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = JobMatchService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        resume_detail = _resume_detail()
        context = CandidateMatchContext(skills={"python", "fastapi", "postgresql"})

        repo_patch, job_patch = _patch_repos(profile, job, resume_detail, context)
        with repo_patch, job_patch:
            result = await service.get_job_match_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is not None
        assert result.job_id == "job-1"
        assert result.job_title == "Senior Backend Engineer"
        assert result.match_score == 82.0
        assert result.matching_skills == ["Python", "FastAPI"]
        assert result.missing_skills == ["Kubernetes"]
        assert result.hiring_recommendation == "Good Fit"
        assert "alignment" in result.experience_match_analysis

        # Prompt should include candidate + job signal, proving the AI call
        # was grounded in real data rather than being called blind.
        prompt = ai_service.last_call["user_prompt"]
        assert "Senior Backend Engineer" in prompt
        assert "Python" in prompt
        assert "Acme Corp" in prompt

    asyncio.run(run_test())


def test_invalid_hiring_recommendation_falls_back_to_score_based_label():
    async def run_test():
        bad_response = dict(VALID_AI_RESPONSE)
        bad_response["hiring_recommendation"] = "Definitely Hire"
        bad_response["match_score"] = 90

        ai_service = FakeAIService(response=bad_response)
        service = JobMatchService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.get_job_match_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result.hiring_recommendation == "Excellent Fit"

    asyncio.run(run_test())


def test_out_of_range_score_is_clamped():
    async def run_test():
        response = dict(VALID_AI_RESPONSE)
        response["match_score"] = 145

        ai_service = FakeAIService(response=response)
        service = JobMatchService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.get_job_match_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result.match_score == 100.0

    asyncio.run(run_test())


def test_malformed_list_fields_are_sanitized_not_raised():
    async def run_test():
        response = dict(VALID_AI_RESPONSE)
        response["matching_skills"] = "Python"  # not a list
        response["strengths"] = [None, "", "  Good communicator  ", {"nested": "dict"}]

        ai_service = FakeAIService(response=response)
        service = JobMatchService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.get_job_match_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result.matching_skills == []  # non-list input -> empty, not a crash
        assert result.strengths == ["Good communicator"]

    asyncio.run(run_test())


def test_ai_service_error_raises_http_503():
    async def run_test():
        ai_service = FakeAIService(error=AIServiceError("Bedrock is down"))
        service = JobMatchService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.get_job_match_score(FakeSession(), uuid4(), "job-1")

        assert exc_info.value.status_code == 503

    asyncio.run(run_test())


def test_works_without_a_resume_on_file():
    """A candidate with a profile but no uploaded resume should still get
    a score, using profile fields only."""

    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = JobMatchService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})

        repo_patch, job_patch = _patch_repos(profile, job, None, context)
        with repo_patch, job_patch:
            result = await service.get_job_match_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is not None
        assert result.match_score == 82.0

    asyncio.run(run_test())
    