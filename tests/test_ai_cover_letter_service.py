"""Unit tests for `AICoverLetterService`.

Mirrors `tests/test_ai_profile_writer_service.py`: repository calls are
patched so no real DB is touched, and Bedrock is replaced with a
`FakeAIService` so no real AWS call is ever made.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schema.ai_cover_letter import (
    AICoverLetterLength,
    AICoverLetterRequest,
    AICoverLetterTone,
)
from app.service.ai_cover_letter_service import AICoverLetterService
from app.service.ai_service import AIInvocationResult, AIServiceError
from app.service.candidate_job_recommendation_engine import CandidateMatchContext


class FakeSession:
    """Placeholder session -- every DB call is mocked at the repository
    layer, so the session object itself is never touched."""


class FakeAIService:
    """Stand-in for `AIService` injected via
    `AICoverLetterService(ai_service=...)` so tests never touch
    boto3/Bedrock."""

    def __init__(self, content: str | None = None, error: Exception | None = None):
        self._content = content
        self._error = error
        self.last_call = None

    async def ainvoke_with_usage(self, **kwargs):
        self.last_call = kwargs
        if self._error:
            raise self._error
        return AIInvocationResult(content=self._content or "")


def _user(**overrides) -> SimpleNamespace:
    base = dict(first_name="Jane", last_name="Doe")
    base.update(overrides)
    return SimpleNamespace(**base)


def _profile(**overrides) -> SimpleNamespace:
    base = dict(
        candidate_id="candidate-1",
        user_id=uuid4(),
        headline="Backend Engineer",
        summary="6 years building backend systems.",
        total_experience=6,
        current_company="Acme Corp",
        experience_level="Senior",
        target_roles="Senior Backend Engineer",
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
                    "key_highlights": "Built and maintained the core API platform.",
                },
            ]
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _job(**overrides) -> SimpleNamespace:
    base = dict(
        job_id="job-1",
        title="Senior Backend Engineer",
        company_name="Globex Corp",
        location="Remote",
        employment_type="Full-time",
        work_mode="Remote",
        description="We are looking for a backend engineer to build APIs.",
        responsibilities=["Design APIs", "Mentor engineers"],
        requirements=["5+ years Python", "AWS experience"],
        skills=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_repos(profile, resume_detail, candidate_context, job, user=None):
    ctx = patch.multiple(
        "app.service.ai_cover_letter_service.CandidateJobRecommendationRepo",
        get_candidate_profile=AsyncMock(return_value=profile),
        get_latest_resume_detail=AsyncMock(return_value=resume_detail),
        build_candidate_match_context=AsyncMock(return_value=candidate_context),
    )
    job_patch = patch(
        "app.service.ai_cover_letter_service.JobRepository.get_job_by_id",
        AsyncMock(return_value=job),
    )
    user_patch = patch(
        "app.service.ai_cover_letter_service.UsersRepository.find_by_user_id",
        AsyncMock(return_value=user or _user()),
    )
    return ctx, job_patch, user_patch


def test_returns_none_when_candidate_profile_missing():
    async def run_test():
        ai_service = FakeAIService(content="Dear Hiring Team, ...")
        service = AICoverLetterService(ai_service=ai_service)
        request = AICoverLetterRequest(job_id="job-1")

        ctx, job_patch, user_patch = _patch_repos(None, _resume_detail(), None, _job())
        with ctx, job_patch, user_patch:
            result = await service.generate(FakeSession(), uuid4(), request)

        assert result is None
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_raises_404_when_job_missing():
    async def run_test():
        ai_service = FakeAIService(content="Dear Hiring Team, ...")
        service = AICoverLetterService(ai_service=ai_service)
        request = AICoverLetterRequest(job_id="does-not-exist")

        profile = _profile()
        ctx, job_patch, user_patch = _patch_repos(profile, _resume_detail(), None, None)
        with ctx, job_patch, user_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.generate(FakeSession(), uuid4(), request)

        assert exc_info.value.status_code == 404
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_generate_builds_prompt_from_candidate_and_job_and_returns_letter():
    async def run_test():
        letter_text = "Dear Hiring Team,\n\nI am excited to apply for the Senior Backend Engineer role."
        ai_service = FakeAIService(content=letter_text)
        service = AICoverLetterService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python", "fastapi"})
        request = AICoverLetterRequest(
            job_id="job-1",
            tone=AICoverLetterTone.CONFIDENT,
            length=AICoverLetterLength.SHORT,
            additional_notes="Mention my open-source contributions.",
        )

        ctx, job_patch, user_patch = _patch_repos(profile, _resume_detail(), context, job)
        with ctx, job_patch, user_patch:
            result = await service.generate(FakeSession(), uuid4(), request)

        assert result is not None
        assert result.cover_letter_text == letter_text
        assert result.job_id == "job-1"
        assert result.job_title == "Senior Backend Engineer"
        assert result.company_name == "Globex Corp"

        # Candidate + job facts should be present in the prompt; the model
        # should never be asked to invent them.
        user_prompt = ai_service.last_call["user_prompt"]
        assert "Acme Corp" in user_prompt  # candidate's real current company
        assert "Globex Corp" in user_prompt  # job's real company
        assert "Senior Backend Engineer" in user_prompt
        assert "open-source contributions" in user_prompt

        system_prompt = ai_service.last_call["system_prompt"]
        assert "confident" in system_prompt.lower()

    asyncio.run(run_test())


def test_existing_text_triggers_revise_instruction():
    async def run_test():
        ai_service = FakeAIService(content="Revised letter text.")
        service = AICoverLetterService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills={"python"})
        request = AICoverLetterRequest(
            job_id="job-1",
            existing_text="Dear Hiring Team, here is my draft.",
        )

        ctx, job_patch, user_patch = _patch_repos(profile, _resume_detail(), context, job)
        with ctx, job_patch, user_patch:
            result = await service.generate(FakeSession(), uuid4(), request)

        assert result.cover_letter_text == "Revised letter text."
        system_prompt = ai_service.last_call["system_prompt"]
        assert "Revise it" in system_prompt
        user_prompt = ai_service.last_call["user_prompt"]
        assert "CANDIDATE'S CURRENT DRAFT" in user_prompt
        assert "here is my draft" in user_prompt

    asyncio.run(run_test())


def test_ai_service_error_raises_http_exception():
    async def run_test():
        ai_service = FakeAIService(error=AIServiceError("boom", category="PROVIDER_UNAVAILABLE"))
        service = AICoverLetterService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills=set())
        request = AICoverLetterRequest(job_id="job-1")

        ctx, job_patch, user_patch = _patch_repos(profile, _resume_detail(), context, job)
        with ctx, job_patch, user_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.generate(FakeSession(), uuid4(), request)

        assert exc_info.value.status_code == 503

    asyncio.run(run_test())


def test_empty_ai_output_raises_502():
    async def run_test():
        ai_service = FakeAIService(content="   ")
        service = AICoverLetterService(ai_service=ai_service)

        profile = _profile()
        job = _job()
        context = CandidateMatchContext(skills=set())
        request = AICoverLetterRequest(job_id="job-1")

        ctx, job_patch, user_patch = _patch_repos(profile, _resume_detail(), context, job)
        with ctx, job_patch, user_patch:
            with pytest.raises(HTTPException) as exc_info:
                await service.generate(FakeSession(), uuid4(), request)

        assert exc_info.value.status_code == 502

    asyncio.run(run_test())