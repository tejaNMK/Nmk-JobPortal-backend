"""Route/auth/schema contract tests for the ATS resume analysis endpoint."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.controller.candidate_controller.candidate_ats_resume_analysis import router
from app.dependencies.role_dependencies import candidate_only
from app.exception_handlers import register_exception_handlers
from app.schema.ats_resume_analysis import ATSResumeAnalysisResponse

USER_ID = uuid4()
SUCCESS_RESULT = ATSResumeAnalysisResponse.model_validate({
    "general_analysis": {
        "scores": {
            "overall_score": 80, "keyword_skill_match_score": 78,
            "experience_relevance_score": 82, "resume_structure_formatting_score": 76,
            "content_quality_score": 81,
        },
        "detected_skills": ["Python"], "detected_roles": ["Backend Engineer"],
        "missing_keywords_or_skills": [], "detected_issues": [],
        "improvement_suggestions": ["Add measurable outcomes."],
    },
    "job_specific_analysis": None,
})


@pytest.fixture()
def client():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    async def fake_candidate_only():
        return {"user_id": str(USER_ID)}

    app.dependency_overrides[candidate_only] = fake_candidate_only
    return TestClient(app)


def test_ats_analysis_returns_valid_response_envelope(client):
    with patch(
        "app.controller.candidate_controller.candidate_ats_resume_analysis.ATSResumeAnalysisService.analyze",
        new=AsyncMock(return_value=SUCCESS_RESULT),
    ) as analyze:
        response = client.post("/candidate/resume/ats-analysis", headers={"Authorization": "Bearer test"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["general_analysis"]["scores"]["overall_score"] == 80
    assert "job_specific_analysis" not in body["data"]
    analyze.assert_awaited_once()


@pytest.mark.parametrize("job_description", ["", "   "])
def test_empty_job_description_is_rejected(client, job_description):
    response = client.post(
        "/candidate/resume/ats-analysis",
        json={"job_description": job_description},
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 422


def test_requires_candidate_authorization():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    async def forbidden():
        raise HTTPException(status_code=403, detail="Only candidates can access this resource")

    app.dependency_overrides[candidate_only] = forbidden
    response = TestClient(app).post("/candidate/resume/ats-analysis")
    assert response.status_code == 403
