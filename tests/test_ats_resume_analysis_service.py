"""Unit tests for the AI ATS resume analyzer without database or Bedrock access."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schema.ats_resume_analysis import ATSResumeAnalysisRequest
from app.service.ai_service import AIServiceError
from app.service.ats_resume_analysis_service import ATSResumeAnalysisService


class FakeSession:
    pass


class FakeAIService:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.last_call = None

    def invoke_json(self, **kwargs):
        self.last_call = kwargs
        if self.error:
            raise self.error
        return self.response


PROFILE = SimpleNamespace(candidate_id="candidate-1")
RESUME_DETAIL = SimpleNamespace(
    experience_json={"experience": [{"role": "Backend Engineer", "company": "Acme", "key_highlights": "Built APIs."}]},
    education_json={"education": [{"degree": "B.Tech", "institution": "State University"}]},
    skills_json={"skills": ["Python", "FastAPI", "AWS"]},
    projects_json={"projects": [{"name": "Payments API"}]},
    certifications_json={"certifications": ["AWS Certified Developer"]},
    languages_json={"languages": ["English"]},
)
VALID_RESPONSE = {
    "general_analysis": {
        "scores": {
            "overall_score": 78,
            "keyword_skill_match_score": 72,
            "experience_relevance_score": 80,
            "resume_structure_formatting_score": 84,
            "content_quality_score": 76,
        },
        "detected_skills": ["Python", "FastAPI", "AWS"],
        "detected_roles": ["Backend Engineer"],
        "missing_keywords_or_skills": ["Docker"],
        "detected_issues": ["Experience bullets lack measurable outcomes."],
        "improvement_suggestions": ["Add outcome metrics to API delivery bullets."],
    },
    "job_specific_analysis": None,
}


def _repos(profile=PROFILE, detail=RESUME_DETAIL):
    return patch.multiple(
        "app.service.ats_resume_analysis_service.CandidateJobRecommendationRepo",
        get_candidate_profile=AsyncMock(return_value=profile),
        get_latest_resume_detail=AsyncMock(return_value=detail),
    )


def test_successful_general_and_job_specific_ats_analysis():
    async def run():
        response = {**VALID_RESPONSE, "job_specific_analysis": {
            "job_specific_score": 74,
            "matched_keywords_or_skills": ["Python", "FastAPI"],
            "missing_keywords_or_skills": ["Kubernetes"],
            "experience_relevance_score": 77,
            "detected_issues": ["Kubernetes experience is not evidenced."],
            "improvement_suggestions": ["Add Kubernetes experience only if accurate."],
        }}
        ai = FakeAIService(response=response)
        with _repos():
            result = await ATSResumeAnalysisService(ai).analyze(
                FakeSession(), uuid4(), ATSResumeAnalysisRequest(job_description="Need Python, FastAPI and Kubernetes experience.")
            )

        assert result.general_analysis.scores.overall_score == 78
        assert result.job_specific_analysis.job_specific_score == 74
        assert "JOB DESCRIPTION" in ai.last_call["user_prompt"]
        assert "AWS" in ai.last_call["user_prompt"]

    asyncio.run(run())


def test_resume_not_found_and_empty_saved_resume_are_rejected():
    async def run():
        with _repos(detail=None):
            with pytest.raises(HTTPException, match="Resume not found") as exc:
                await ATSResumeAnalysisService(FakeAIService(VALID_RESPONSE)).analyze(FakeSession(), uuid4(), ATSResumeAnalysisRequest())
        assert exc.value.status_code == 404

        empty_detail = SimpleNamespace(
            experience_json=None, education_json=None, skills_json=None, projects_json=None,
            certifications_json=None, languages_json=None,
        )
        with _repos(detail=empty_detail):
            with pytest.raises(HTTPException, match="no analyzable content") as exc:
                await ATSResumeAnalysisService(FakeAIService(VALID_RESPONSE)).analyze(FakeSession(), uuid4(), ATSResumeAnalysisRequest())
        assert exc.value.status_code == 400

        with _repos(), patch(
            "app.service.ats_resume_analysis_service.CandidateProfileRepo.get_resume",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException, match="Resume not found") as exc:
                await ATSResumeAnalysisService(FakeAIService(VALID_RESPONSE)).analyze(
                    FakeSession(), uuid4(), ATSResumeAnalysisRequest(resume_id="missing-resume")
                )
        assert exc.value.status_code == 404

        uploaded_resume = SimpleNamespace(blob_ref="resumes/unreadable.pdf", file_name="unreadable.pdf")
        with _repos(), patch(
            "app.service.ats_resume_analysis_service.CandidateProfileRepo.get_resume",
            new=AsyncMock(return_value=uploaded_resume),
        ), patch(
            "app.service.ats_resume_analysis_service.s3_service.fetch_object_bytes",
            return_value=(b"not a readable resume", "application/pdf"),
        ), patch(
            "app.service.ats_resume_analysis_service.resume_extraction.extract_resume_data",
            return_value=None,
        ):
            with pytest.raises(HTTPException, match="could not be analyzed") as exc:
                await ATSResumeAnalysisService(FakeAIService(VALID_RESPONSE)).analyze(
                    FakeSession(), uuid4(), ATSResumeAnalysisRequest(resume_id="unreadable-resume")
                )
        assert exc.value.status_code == 400

    asyncio.run(run())


def test_provider_failure_is_safely_translated():
    async def run():
        ai = FakeAIService(error=AIServiceError("Bedrock unavailable", category="PROVIDER_UNAVAILABLE"))
        with _repos():
            with pytest.raises(HTTPException, match="ATS analyzer is temporarily unavailable") as exc:
                await ATSResumeAnalysisService(ai).analyze(FakeSession(), uuid4(), ATSResumeAnalysisRequest())
        assert exc.value.status_code == 503

    asyncio.run(run())


def test_invalid_provider_response_is_rejected():
    async def run():
        with _repos():
            with pytest.raises(HTTPException, match="invalid result") as exc:
                await ATSResumeAnalysisService(FakeAIService(response={"general_analysis": {}})).analyze(
                    FakeSession(), uuid4(), ATSResumeAnalysisRequest()
                )
        assert exc.value.status_code == 502

    asyncio.run(run())
