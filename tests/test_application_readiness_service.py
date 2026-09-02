from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.service.ai_service import AIServiceError
from app.service.application_readiness_service import ApplicationReadinessService
from app.service.candidate_job_recommendation_engine import CandidateMatchContext


class FakeSession:
    """Placeholder session — every DB call in these tests is mocked at the
    repository layer, so the session object itself is never touched."""


class FakeAIService:
    """Stand-in for `AIService` injected via
    `ApplicationReadinessService(ai_service=...)` so tests never touch
    boto3/Bedrock — same pattern as `tests/test_job_match_service.py`."""

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
        salary_min=None,
        salary_max=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


VALID_AI_RESPONSE = {
    "resume_match_score": 75,
    "interview_readiness_score": 65,
    "strengths": ["Deep backend expertise"],
    "weaknesses": ["No container orchestration experience listed"],
    "gaps": ["Resume lacks quantified achievements"],
    "improvement_suggestions": ["Add measurable impact metrics to recent roles"],
    "readiness_explanation": "Strong technical fit with room to sharpen the resume.",
}


def _patch_repos(profile, job, resume_detail, candidate_context):
    return patch.multiple(
        "app.service.application_readiness_service.CandidateJobRecommendationRepo",
        get_candidate_profile=AsyncMock(return_value=profile),
        get_latest_resume_detail=AsyncMock(return_value=resume_detail),
        build_candidate_match_context=AsyncMock(return_value=candidate_context),
    ), patch(
        "app.service.application_readiness_service.CandidateJobSearchRepo.get_job_details",
        new=AsyncMock(return_value=job),
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
        service = ApplicationReadinessService(ai_service=ai_service)

        repo_patch, job_patch = _patch_repos(None, _job(), _resume_detail(), None)
        with repo_patch, job_patch:
            result = await service.get_application_readiness_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is None
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_returns_none_when_job_not_found():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = ApplicationReadinessService(ai_service=ai_service)
        profile = _profile()

        repo_patch, job_patch = _patch_repos(profile, None, _resume_detail(), None)
        with repo_patch, job_patch:
            result = await service.get_application_readiness_score(
                FakeSession(), uuid4(), "missing-job"
            )

        assert result is None
        assert ai_service.last_call is None

    asyncio.run(run_test())


def test_returns_mapped_response_on_successful_ai_call():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = ApplicationReadinessService(ai_service=ai_service)

        profile = _profile(profile_completion_pct=70)
        job = _job()
        resume_detail = _resume_detail()
        context = _full_context()

        repo_patch, job_patch = _patch_repos(profile, job, resume_detail, context)
        with repo_patch, job_patch:
            result = await service.get_application_readiness_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is not None
        assert result.job_id == "job-1"
        assert result.job_title == "Senior Backend Engineer"

        # Deterministic factors.
        assert result.profile_completeness_score == 70.0
        assert result.experience_match_score == 100.0  # 6 years within 5-8 range
        assert result.skills_match_score > 0
        assert result.matched_skills == ["python"] or "python" in [
            s.lower() for s in result.matched_skills
        ]
        assert "kubernetes" in [s.lower() for s in result.missing_skills]

        # AI factors, passed through as clamped floats.
        assert result.resume_match_score == 75.0
        assert result.interview_readiness_score == 65.0
        assert result.strengths == ["Deep backend expertise"]
        assert result.gaps == ["Resume lacks quantified achievements"]
        assert "sharpen" in result.readiness_explanation

        # overall_score is a deterministic weighted composite -- never
        # AI-generated -- and must fall strictly between the lowest and
        # highest individual factor scores.
        factors = [
            result.resume_match_score,
            result.skills_match_score,
            result.experience_match_score,
            result.profile_completeness_score,
            result.interview_readiness_score,
        ]
        assert min(factors) <= result.overall_score <= max(factors)

        # Prompt should include candidate + job signal, proving the AI call
        # was grounded in real data rather than being called blind.
        prompt = ai_service.last_call["user_prompt"]
        assert "Senior Backend Engineer" in prompt
        assert "Python" in prompt
        assert "Acme Corp" in prompt
        assert "Missing skills (already computed)" in prompt

    asyncio.run(run_test())


def test_overall_score_matches_weighted_formula():
    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = ApplicationReadinessService(ai_service=ai_service)

        profile = _profile(profile_completion_pct=70)
        job = _job()
        context = _full_context()

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.get_application_readiness_score(
                FakeSession(), uuid4(), "job-1"
            )

        expected = round(
            (
                result.resume_match_score * 25
                + result.skills_match_score * 25
                + result.experience_match_score * 20
                + result.profile_completeness_score * 15
                + result.interview_readiness_score * 15
            )
            / 100.0,
            2,
        )
        assert result.overall_score == expected

    asyncio.run(run_test())


def test_out_of_range_ai_scores_are_clamped():
    async def run_test():
        response = dict(VALID_AI_RESPONSE)
        response["resume_match_score"] = 145
        response["interview_readiness_score"] = -20

        ai_service = FakeAIService(response=response)
        service = ApplicationReadinessService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.get_application_readiness_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result.resume_match_score == 100.0
        assert result.interview_readiness_score == 0.0

    asyncio.run(run_test())


def test_malformed_list_fields_are_sanitized_not_raised():
    async def run_test():
        response = dict(VALID_AI_RESPONSE)
        response["strengths"] = "Python"  # not a list
        response["gaps"] = [None, "", "  Thin resume detail  ", {"nested": "dict"}]

        ai_service = FakeAIService(response=response)
        service = ApplicationReadinessService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            result = await service.get_application_readiness_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result.strengths == []  # non-list input -> empty, not a crash
        assert result.gaps == ["Thin resume detail"]

    asyncio.run(run_test())


def test_ai_service_error_raises_http_error():
    async def run_test():
        ai_service = FakeAIService(error=AIServiceError("Bedrock is down"))
        service = ApplicationReadinessService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, job_patch = _patch_repos(profile, job, _resume_detail(), context)
        with repo_patch, job_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.get_application_readiness_score(
                    FakeSession(), uuid4(), "job-1"
                )

        assert exc_info.value.status_code in (502, 503)

    asyncio.run(run_test())


def test_works_without_a_resume_on_file():
    """A candidate with a profile but no uploaded resume should still get
    a score, using profile fields only."""

    async def run_test():
        ai_service = FakeAIService(response=VALID_AI_RESPONSE)
        service = ApplicationReadinessService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = _full_context()

        repo_patch, job_patch = _patch_repos(profile, job, None, context)
        with repo_patch, job_patch:
            result = await service.get_application_readiness_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result is not None
        assert result.resume_match_score == 75.0

    asyncio.run(run_test())


def test_zero_skills_and_zero_completion_yields_low_overall_score():
    async def run_test():
        low_ai_response = {
            "resume_match_score": 0,
            "interview_readiness_score": 0,
            "strengths": [],
            "weaknesses": ["No relevant experience shown"],
            "gaps": ["Profile is nearly empty"],
            "improvement_suggestions": ["Complete your profile"],
            "readiness_explanation": "The candidate is not yet ready to apply.",
        }
        ai_service = FakeAIService(response=low_ai_response)
        service = ApplicationReadinessService(ai_service=ai_service)

        profile = _profile(profile_completion_pct=0)
        job = _job(experience_min=10, experience_max=15)  # far outside candidate's range
        context = CandidateMatchContext(
            skills=set(),
            total_experience_years=6,
            profile_completion_pct=0,
        )

        repo_patch, job_patch = _patch_repos(profile, job, None, context)
        with repo_patch, job_patch:
            result = await service.get_application_readiness_score(
                FakeSession(), uuid4(), "job-1"
            )

        assert result.overall_score < 20.0

    asyncio.run(run_test())