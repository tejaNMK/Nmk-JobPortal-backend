"""Unit tests for `AIProfileWriterService`.

Mirrors `tests/test_job_match_service.py`: repository calls are patched so
no real DB is touched, and Bedrock is replaced with a `FakeAIService` so no
real AWS call is ever made.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schema.ai_profile_writer import AIProfileWriterSection
from app.service.ai_service import AIServiceError
from app.service.candidate_job_recommendation_engine import CandidateMatchContext
from app.service.ai_profile_writer_service import AIProfileWriterService


class FakeSession:
    """Placeholder session — every DB call is mocked at the repository
    layer, so the session object itself is never touched."""


class FakeAIService:
    """Stand-in for `AIService` injected via
    `AIProfileWriterService(ai_service=...)` so tests never touch
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
                    "key_highlights": "Worked on the core API platform.",
                },
                {
                    "role": "Junior Developer",
                    "company": "Globex",
                    "start_date": "2018-01",
                    "end_date": "2019-12",
                    "currently_working": False,
                    "key_highlights": "Helped build internal tools.",
                },
            ]
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


VALID_FULL_RESPONSE = {
    "headline": "Senior Backend Engineer | Python, FastAPI, AWS",
    "professional_summary": "Backend engineer with 6+ years building scalable APIs.",
    "experience": [
        {"description": "Built the core API platform.\nImproved latency by 35%."},
        {"description": "Helped build internal developer tools."},
    ],
}


def _patch_repos(profile, resume_detail, candidate_context):
    return patch.multiple(
        "app.service.ai_profile_writer_service.CandidateJobRecommendationRepo",
        get_candidate_profile=AsyncMock(return_value=profile),
        get_latest_resume_detail=AsyncMock(return_value=resume_detail),
        build_candidate_match_context=AsyncMock(return_value=candidate_context),
    )


def test_returns_none_when_candidate_profile_missing():
    async def run_test():
        ai_service = FakeAIService(response=VALID_FULL_RESPONSE)
        service = AIProfileWriterService(ai_service=ai_service)

        with _patch_repos(None, _resume_detail(), None):
            result = await service.generate_profile_content(FakeSession(), uuid4())

        assert result is None
        assert ai_service.last_call is None  # never reached Bedrock

    asyncio.run(run_test())


def test_generate_all_sections_maps_response_and_preserves_title_company():
    async def run_test():
        ai_service = FakeAIService(response=VALID_FULL_RESPONSE)
        service = AIProfileWriterService(ai_service=ai_service)

        profile = _profile()
        resume_detail = _resume_detail()
        context = CandidateMatchContext(skills={"python", "fastapi"})

        with _patch_repos(profile, resume_detail, context):
            result = await service.generate_profile_content(FakeSession(), uuid4())

        assert result is not None
        assert result.headline == "Senior Backend Engineer | Python, FastAPI, AWS"
        assert result.professional_summary.startswith("Backend engineer")
        assert len(result.experience) == 2

        # title/company must come from the candidate's OWN resume data,
        # never from the AI response (which didn't even include them).
        assert result.experience[0].title == "Backend Engineer"
        assert result.experience[0].company == "Acme Corp"
        assert "Built the core API platform" in result.experience[0].description

        assert result.experience[1].title == "Junior Developer"
        assert result.experience[1].company == "Globex"

        prompt = ai_service.last_call["user_prompt"]
        assert "Senior Backend Engineer" in prompt  # target role from profile
        assert "Acme Corp" in prompt

    asyncio.run(run_test())


def test_regenerate_single_section_only_populates_that_field():
    async def run_test():
        ai_service = FakeAIService(response={"headline": "Lead Platform Engineer"})
        service = AIProfileWriterService(ai_service=ai_service)

        profile = _profile()
        context = CandidateMatchContext(skills={"python"})

        with _patch_repos(profile, _resume_detail(), context):
            result = await service.regenerate_section(
                FakeSession(), uuid4(), AIProfileWriterSection.HEADLINE
            )

        assert result.headline == "Lead Platform Engineer"
        assert result.professional_summary is None
        assert result.experience is None

        # Only the headline instruction should be in the system prompt.
        system_prompt = ai_service.last_call["system_prompt"]
        assert '"headline"' in system_prompt
        assert '"professional_summary"' not in system_prompt

    asyncio.run(run_test())


def test_experience_section_falls_back_to_original_text_when_ai_omits_entry():
    async def run_test():
        # AI only returns one description even though the candidate has two
        # experience entries -- the second must fall back to the
        # candidate's own existing text rather than being blank/invented.
        response = {"experience": [{"description": "Rewritten first role."}]}
        ai_service = FakeAIService(response=response)
        service = AIProfileWriterService(ai_service=ai_service)

        profile = _profile()
        context = CandidateMatchContext(skills=set())

        with _patch_repos(profile, _resume_detail(), context):
            result = await service.regenerate_section(
                FakeSession(), uuid4(), AIProfileWriterSection.EXPERIENCE
            )

        assert result.experience[0].description == "Rewritten first role."
        assert result.experience[1].description == "Helped build internal tools."
        assert result.experience[1].company == "Globex"

    asyncio.run(run_test())


def test_experience_section_with_no_resume_entries_returns_empty_list_without_calling_ai():
    async def run_test():
        ai_service = FakeAIService(response=VALID_FULL_RESPONSE)
        service = AIProfileWriterService(ai_service=ai_service)

        profile = _profile()
        context = CandidateMatchContext(skills=set())
        empty_resume = _resume_detail(experience_json={"experience": []})

        with _patch_repos(profile, empty_resume, context):
            result = await service.regenerate_section(
                FakeSession(), uuid4(), AIProfileWriterSection.EXPERIENCE
            )

        assert result.experience == []
        assert ai_service.last_call is None  # never called Bedrock for nothing to enhance

    asyncio.run(run_test())


def test_ai_service_error_raises_503():
    async def run_test():
        ai_service = FakeAIService(error=AIServiceError("boom"))
        service = AIProfileWriterService(ai_service=ai_service)

        profile = _profile()
        context = CandidateMatchContext(skills=set())

        with _patch_repos(profile, _resume_detail(), context):
            with pytest.raises(HTTPException) as exc_info:
                await service.generate_profile_content(FakeSession(), uuid4())

        assert exc_info.value.status_code == 503

    asyncio.run(run_test())


def test_malformed_ai_fields_do_not_raise():
    async def run_test():
        response = {
            "headline": 12345,  # not a string
            "professional_summary": None,
            "experience": "not-a-list",
        }
        ai_service = FakeAIService(response=response)
        service = AIProfileWriterService(ai_service=ai_service)

        profile = _profile()
        context = CandidateMatchContext(skills=set())

        with _patch_repos(profile, _resume_detail(), context):
            result = await service.generate_profile_content(FakeSession(), uuid4())

        assert result.headline == ""
        assert result.professional_summary == ""
        # experience falls back entirely to the candidate's own text
        assert result.experience[0].description == "Worked on the core API platform."

    asyncio.run(run_test())
