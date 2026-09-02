"""Controller-level tests for `GET /candidate/jobs/{job_id}/ai-match-score`.

These exercise routing, auth-gating, and the standard `ResponseSchema`
envelope through FastAPI's `TestClient`, with `candidate_only` and `get_db`
overridden (same style as `tests/test_resume_library_controller.py`) so no
real JWT/session/DB is needed, and `JobMatchService.get_job_match_score`
mocked so no real Bedrock call is made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.main import init_app
from app.schema.job_match import JobMatchScoreResponse

USER_ID = uuid4()

CANDIDATE_PAYLOAD = {
    "user_id": str(USER_ID),
    "email": "candidate@example.com",
    "roles": [
        {
            "role_id": "22222222-2222-2222-2222-222222222222",
            "role_name": "Candidate",
            "role_code": "ROLE_CANDIDATE",
        }
    ],
}


class FakeSession:
    async def execute(self, *args, **kwargs):
        return None

    async def commit(self):
        return None


@pytest.fixture()
def client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_candidate_only():
        return CANDIDATE_PAYLOAD

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[candidate_only] = fake_candidate_only
    return TestClient(app)


def _sample_result() -> JobMatchScoreResponse:
    return JobMatchScoreResponse(
        job_id="job-1",
        job_title="Senior Backend Engineer",
        match_score=82.5,
        matching_skills=["Python", "FastAPI"],
        missing_skills=["Kubernetes"],
        experience_match_analysis="Strong alignment with the role.",
        strengths=["Deep backend expertise"],
        weaknesses=["No container orchestration experience"],
        hiring_recommendation="Good Fit",
        improvement_suggestions=["Add Kubernetes exposure to the resume"],
    )


def test_ai_match_score_success_returns_response_envelope(client):
    with patch(
        "app.controller.candidate_controller.candidate_jobs.JobMatchService.get_job_match_score",
        new=AsyncMock(return_value=_sample_result()),
    ) as mock_get:
        response = client.get(
            "/candidate/jobs/job-1/ai-match-score",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "AI job match score generated successfully"
    assert body["data"]["job_id"] == "job-1"
    assert body["data"]["match_score"] == 82.5
    assert body["data"]["hiring_recommendation"] == "Good Fit"
    mock_get.assert_awaited_once()
    _, kwargs = mock_get.call_args
    assert kwargs["job_id"] == "job-1"
    assert str(kwargs["user_id"]) == str(USER_ID)


def test_ai_match_score_returns_404_when_job_or_profile_not_found(client):
    with patch(
        "app.controller.candidate_controller.candidate_jobs.JobMatchService.get_job_match_score",
        new=AsyncMock(return_value=None),
    ):
        response = client.get(
            "/candidate/jobs/missing-job/ai-match-score",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False


def test_ai_match_score_requires_authentication():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    # candidate_only is intentionally NOT overridden here, so the real
    # JWT/session check applies and an unauthenticated request is rejected.
    client = TestClient(app)

    response = client.get("/candidate/jobs/job-1/ai-match-score")

    assert response.status_code in (401, 403)