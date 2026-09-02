"""Controller-level tests for the AI Cover Letter Generator endpoint:

    POST /candidate/cover-letter/generate

These exercise routing, auth-gating, and the standard `ResponseSchema`
envelope through FastAPI's `TestClient`, with `candidate_only` and `get_db`
overridden (same style as `tests/test_ai_profile_writer_controller.py`) so
no real JWT/session/DB is needed, and `AICoverLetterService` is mocked so
no real Bedrock call is made.
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
from app.schema.ai_cover_letter import AICoverLetterResponse

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


def _result() -> AICoverLetterResponse:
    return AICoverLetterResponse(
        cover_letter_text="Dear Hiring Team,\n\nI am excited to apply...",
        job_id="job-1",
        job_title="Senior Backend Engineer",
        company_name="Globex Corp",
    )


def test_generate_success_returns_response_envelope(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_cover_letter.AICoverLetterService.generate",
        new=AsyncMock(return_value=_result()),
    ) as mock_generate:
        response = client.post(
            "/candidate/cover-letter/generate",
            json={"job_id": "job-1"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "AI cover letter generated successfully"
    assert body["data"]["job_id"] == "job-1"
    assert body["data"]["job_title"] == "Senior Backend Engineer"
    assert body["data"]["company_name"] == "Globex Corp"
    assert "excited to apply" in body["data"]["cover_letter_text"]

    mock_generate.assert_awaited_once()
    _, kwargs = mock_generate.call_args
    assert str(kwargs["user_id"]) == str(USER_ID)
    assert kwargs["request"].job_id == "job-1"


def test_generate_with_tone_and_length_passes_them_through(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_cover_letter.AICoverLetterService.generate",
        new=AsyncMock(return_value=_result()),
    ) as mock_generate:
        response = client.post(
            "/candidate/cover-letter/generate",
            json={"job_id": "job-1", "tone": "confident", "length": "short"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    _, kwargs = mock_generate.call_args
    assert kwargs["request"].tone.value == "confident"
    assert kwargs["request"].length.value == "short"


def test_generate_requires_job_id(client):
    response = client.post(
        "/candidate/cover-letter/generate",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 422


def test_generate_returns_404_when_profile_not_found(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_cover_letter.AICoverLetterService.generate",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            "/candidate/cover-letter/generate",
            json={"job_id": "job-1"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False


def test_generate_returns_404_when_job_not_found(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_cover_letter.AICoverLetterService.generate",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Job not found")),
    ):
        response = client.post(
            "/candidate/cover-letter/generate",
            json={"job_id": "does-not-exist"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["details"] == "Job not found"


def test_generate_requires_authentication():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    # candidate_only is intentionally NOT overridden here, so the real
    # JWT/session check applies and an unauthenticated request is rejected.
    client = TestClient(app)

    response = client.post("/candidate/cover-letter/generate", json={"job_id": "job-1"})

    assert response.status_code in (401, 403)