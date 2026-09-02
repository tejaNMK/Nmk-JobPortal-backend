"""Controller-level tests for `GET /candidate/jobs/{job_id}/ai-interview-questions`.

These exercise routing, auth-gating, and the standard `ResponseSchema`
envelope through FastAPI's `TestClient`, with `candidate_only` and `get_db`
overridden (same style as `tests/test_job_match_controller.py`) so no real
JWT/session/DB is needed, and
`AIInterviewQuestionService.generate_interview_questions` mocked so no real
Bedrock call is made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.main import init_app
from app.schema.ai_interview_question import (
    AIInterviewQuestionsResponse,
    InterviewQuestionItem,
)

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


def _sample_result() -> AIInterviewQuestionsResponse:
    return AIInterviewQuestionsResponse(
        job_id="job-1",
        job_title="Senior Backend Engineer",
        company_name="Globex",
        questions=[
            InterviewQuestionItem(
                id=1,
                category="Technical",
                question="How would you design a scalable FastAPI application?",
                sample_answer="I'd start by profiling hot paths and leaning on async I/O.",
            ),
            InterviewQuestionItem(
                id=2,
                category="Behavioral",
                question="Tell me about a time you disagreed with a teammate.",
                sample_answer="At Acme Corp, I raised a concern about an API design early and we found a middle ground.",
            ),
        ],
    )


def test_ai_interview_questions_success_returns_response_envelope(client):
    with patch(
        "app.controller.candidate_controller.candidate_jobs.AIInterviewQuestionService"
        ".generate_interview_questions",
        new=AsyncMock(return_value=_sample_result()),
    ) as mock_get:
        response = client.get(
            "/candidate/jobs/job-1/ai-interview-questions",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "AI interview questions generated successfully"
    assert body["data"]["job_id"] == "job-1"
    assert body["data"]["jobTitle"] == "Senior Backend Engineer"
    assert body["data"]["companyName"] == "Globex"
    assert len(body["data"]["questions"]) == 2
    assert body["data"]["questions"][0]["id"] == 1
    assert body["data"]["questions"][0]["category"] == "Technical"
    assert body["data"]["questions"][0]["sampleAnswer"]
    mock_get.assert_awaited_once()
    _, kwargs = mock_get.call_args
    assert kwargs["job_id"] == "job-1"
    assert str(kwargs["user_id"]) == str(USER_ID)


def test_ai_interview_questions_returns_404_when_job_not_found(client):
    with patch(
        "app.controller.candidate_controller.candidate_jobs.AIInterviewQuestionService"
        ".generate_interview_questions",
        new=AsyncMock(return_value=None),
    ):
        response = client.get(
            "/candidate/jobs/missing-job/ai-interview-questions",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False


def test_ai_interview_questions_returns_403_when_not_applied(client):
    with patch(
        "app.controller.candidate_controller.candidate_jobs.AIInterviewQuestionService"
        ".generate_interview_questions",
        new=AsyncMock(
            side_effect=HTTPException(
                status_code=403,
                detail="You must apply to this job before generating AI interview questions for it.",
            )
        ),
    ):
        response = client.get(
            "/candidate/jobs/job-1/ai-interview-questions",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["success"] is False


def test_ai_interview_questions_returns_503_when_ai_service_unavailable(client):
    with patch(
        "app.controller.candidate_controller.candidate_jobs.AIInterviewQuestionService"
        ".generate_interview_questions",
        new=AsyncMock(
            side_effect=HTTPException(
                status_code=503,
                detail="AI interview question generation is temporarily unavailable. Please try again shortly.",
            )
        ),
    ):
        response = client.get(
            "/candidate/jobs/job-1/ai-interview-questions",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False


def test_ai_interview_questions_requires_authentication():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    # candidate_only is intentionally NOT overridden here, so the real
    # JWT/session check applies and an unauthenticated request is rejected.
    client = TestClient(app)

    response = client.get("/candidate/jobs/job-1/ai-interview-questions")

    assert response.status_code in (401, 403)