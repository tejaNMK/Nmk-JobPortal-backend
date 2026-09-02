"""Controller-level tests for `GET /candidate/jobs/{job_id}/readiness-score`.

These exercise routing, auth-gating, and the standard `ResponseSchema`
envelope through FastAPI's `TestClient`, with `candidate_only` and `get_db`
overridden (same style as `tests/test_job_match_controller.py`) so no real
JWT/session/DB is needed, and
`ApplicationReadinessService.get_application_readiness_score` mocked so no
real Bedrock call is made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.main import init_app
from app.schema.application_readiness import ApplicationReadinessScoreResponse

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


def _sample_result() -> ApplicationReadinessScoreResponse:
    return ApplicationReadinessScoreResponse(
        job_id="job-1",
        job_title="Senior Backend Engineer",
        overall_score=78.4,
        resume_match_score=75.0,
        skills_match_score=82.5,
        experience_match_score=100.0,
        profile_completeness_score=60.0,
        interview_readiness_score=65.0,
        matched_skills=["Python", "FastAPI"],
        missing_skills=["Kubernetes"],
        strengths=["Strong Python/FastAPI background"],
        weaknesses=["No container orchestration experience listed"],
        gaps=["Resume lacks quantified achievements"],
        improvement_suggestions=["Add measurable impact metrics to recent roles"],
        readiness_explanation="Strong technical fit with room to sharpen the resume.",
    )


def test_readiness_score_success_returns_response_envelope(client):
    with patch(
        "app.controller.candidate_controller.candidate_jobs.ApplicationReadinessService"
        ".get_application_readiness_score",
        new=AsyncMock(return_value=_sample_result()),
    ) as mock_get:
        response = client.get(
            "/candidate/jobs/job-1/readiness-score",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Application readiness score generated successfully"
    assert body["data"]["job_id"] == "job-1"
    assert body["data"]["overall_score"] == 78.4
    assert body["data"]["skills_match_score"] == 82.5
    assert body["data"]["missing_skills"] == ["Kubernetes"]
    mock_get.assert_awaited_once()
    _, kwargs = mock_get.call_args
    assert kwargs["job_id"] == "job-1"
    assert str(kwargs["user_id"]) == str(USER_ID)


def test_readiness_score_returns_404_when_job_or_profile_not_found(client):
    with patch(
        "app.controller.candidate_controller.candidate_jobs.ApplicationReadinessService"
        ".get_application_readiness_score",
        new=AsyncMock(return_value=None),
    ):
        response = client.get(
            "/candidate/jobs/missing-job/readiness-score",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False


def test_readiness_score_requires_authentication():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    # candidate_only is intentionally NOT overridden here, so the real
    # JWT/session check applies and an unauthenticated request is rejected.
    client = TestClient(app)

    response = client.get("/candidate/jobs/job-1/readiness-score")

    assert response.status_code in (401, 403)