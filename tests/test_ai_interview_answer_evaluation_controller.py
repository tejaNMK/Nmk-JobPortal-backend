"""Controller-level tests for `POST /candidate/interview-answer/evaluate`.

These exercise routing, auth-gating, request validation, and the standard
`ResponseSchema` envelope through FastAPI's `TestClient`, with
`candidate_only` and `get_db` overridden (same style as
`tests/test_application_readiness_controller.py`) so no real JWT/session/
DB is needed, and
`AIInterviewAnswerEvaluationService.evaluate_answer` mocked so no real
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
from app.schema.ai_interview_answer_evaluation import AIInterviewAnswerEvaluationResponse

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

REQUEST_BODY = {
    "job_id": "job-1",
    "question": "How would you design this role's core service to scale?",
    "answer": "I'd profile the hot paths, then apply async I/O and connection pooling.",
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


def _sample_result() -> AIInterviewAnswerEvaluationResponse:
    return AIInterviewAnswerEvaluationResponse(
        job_id="job-1",
        job_title="Senior Backend Engineer",
        company_name="Globex",
        question=REQUEST_BODY["question"],
        overall_score=72.0,
        technical_accuracy=75.0,
        relevance=80.0,
        clarity=65.0,
        strengths=["Correctly identifies caching and async I/O as levers"],
        areas_for_improvement=["Answer stays generic rather than giving a concrete example"],
        detailed_feedback="Solid awareness of scaling concepts but stays generic.",
        suggested_improved_answer="I'd start by profiling the hot paths in the service...",
    )


def test_evaluate_success_returns_response_envelope(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_interview_answer_evaluation"
        ".AIInterviewAnswerEvaluationService.evaluate_answer",
        new=AsyncMock(return_value=_sample_result()),
    ) as mock_evaluate:
        response = client.post(
            "/candidate/interview-answer/evaluate",
            json=REQUEST_BODY,
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Interview answer evaluated successfully"
    assert body["data"]["job_id"] == "job-1"
    assert body["data"]["overall_score"] == 72.0
    assert body["data"]["technical_accuracy"] == 75.0
    assert body["data"]["question"] == REQUEST_BODY["question"]
    mock_evaluate.assert_awaited_once()
    _, kwargs = mock_evaluate.call_args
    assert str(kwargs["user_id"]) == str(USER_ID)
    assert kwargs["request"].job_id == "job-1"


def test_evaluate_returns_404_when_job_or_profile_not_found(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_interview_answer_evaluation"
        ".AIInterviewAnswerEvaluationService.evaluate_answer",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            "/candidate/interview-answer/evaluate",
            json=REQUEST_BODY,
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False


def test_evaluate_returns_403_when_candidate_has_not_applied(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_interview_answer_evaluation"
        ".AIInterviewAnswerEvaluationService.evaluate_answer",
        new=AsyncMock(
            side_effect=HTTPException(
                status_code=403, detail="You must apply to this job first."
            )
        ),
    ):
        response = client.post(
            "/candidate/interview-answer/evaluate",
            json=REQUEST_BODY,
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 403


def test_evaluate_rejects_blank_answer(client):
    bad_body = dict(REQUEST_BODY, answer="   ")
    response = client.post(
        "/candidate/interview-answer/evaluate",
        json=bad_body,
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 422


def test_evaluate_requires_authentication():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    # candidate_only is intentionally NOT overridden here, so the real
    # JWT/session check applies and an unauthenticated request is rejected.
    client = TestClient(app)

    response = client.post("/candidate/interview-answer/evaluate", json=REQUEST_BODY)

    assert response.status_code in (401, 403)