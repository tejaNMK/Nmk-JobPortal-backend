"""Controller-level tests for the AI Resume/Profile Writer endpoints:

    POST /candidate/profile/ai-writer/generate
    POST /candidate/profile/ai-writer/regenerate

These exercise routing, auth-gating, and the standard `ResponseSchema`
envelope through FastAPI's `TestClient`, with `candidate_only` and `get_db`
overridden (same style as `tests/test_job_match_controller.py`) so no real
JWT/session/DB is needed, and `AIProfileWriterService` is mocked so no real
Bedrock call is made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.main import init_app
from app.schema.ai_profile_writer import AIProfileExperienceEntry, AIProfileWriterResponse

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


def _full_result() -> AIProfileWriterResponse:
    return AIProfileWriterResponse(
        headline="Senior Backend Engineer | Python, FastAPI, AWS",
        professional_summary="Backend engineer with 6+ years building scalable APIs.",
        experience=[
            AIProfileExperienceEntry(
                title="Backend Engineer",
                company="Acme Corp",
                description="Built the core API platform.\nImproved latency by 35%.",
            )
        ],
    )


def _headline_only_result() -> AIProfileWriterResponse:
    return AIProfileWriterResponse(headline="Lead Platform Engineer")


def test_generate_success_returns_response_envelope(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_profile_writer.AIProfileWriterService.generate_profile_content",
        new=AsyncMock(return_value=_full_result()),
    ) as mock_generate:
        response = client.post(
            "/candidate/profile/ai-writer/generate",
            json={},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "AI profile content generated successfully"
    assert body["data"]["headline"] == "Senior Backend Engineer | Python, FastAPI, AWS"
    assert body["data"]["experience"][0]["title"] == "Backend Engineer"
    assert body["data"]["experience"][0]["company"] == "Acme Corp"
    mock_generate.assert_awaited_once()
    _, kwargs = mock_generate.call_args
    assert str(kwargs["user_id"]) == str(USER_ID)


def test_generate_with_target_role_passes_it_through(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_profile_writer.AIProfileWriterService.generate_profile_content",
        new=AsyncMock(return_value=_full_result()),
    ) as mock_generate:
        response = client.post(
            "/candidate/profile/ai-writer/generate",
            json={"target_role": "Staff Engineer"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    _, kwargs = mock_generate.call_args
    assert kwargs["target_role"] == "Staff Engineer"


def test_generate_returns_404_when_profile_not_found(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_profile_writer.AIProfileWriterService.generate_profile_content",
        new=AsyncMock(return_value=None),
    ):
        response = client.post(
            "/candidate/profile/ai-writer/generate",
            json={},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False


def test_regenerate_single_section_only_returns_that_field(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_profile_writer.AIProfileWriterService.regenerate_section",
        new=AsyncMock(return_value=_headline_only_result()),
    ) as mock_regenerate:
        response = client.post(
            "/candidate/profile/ai-writer/regenerate",
            json={"section": "headline"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"headline": "Lead Platform Engineer"}
    assert "professional_summary" not in body["data"]
    assert "experience" not in body["data"]
    _, kwargs = mock_regenerate.call_args
    assert kwargs["section"].value == "headline"


def test_regenerate_requires_valid_section(client):
    response = client.post(
        "/candidate/profile/ai-writer/regenerate",
        json={"section": "not-a-real-section"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 422


def test_generate_requires_authentication():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    # candidate_only is intentionally NOT overridden here, so the real
    # JWT/session check applies and an unauthenticated request is rejected.
    client = TestClient(app)

    response = client.post("/candidate/profile/ai-writer/generate", json={})

    assert response.status_code in (401, 403)
