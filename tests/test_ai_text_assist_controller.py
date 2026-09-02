"""Controller-level tests for:

    POST /candidate/resume/ai-text-assist

Exercises routing, auth-gating, and the standard `ResponseSchema` envelope
through FastAPI's `TestClient`, with `candidate_only` overridden (same
style as `tests/test_ai_profile_writer_controller.py`) so no real JWT is
needed, and `AITextAssistService` is mocked so no real Bedrock call is
made. No `get_db` override is needed here -- unlike the AI Profile Writer
endpoints, this feature never touches the database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies.role_dependencies import candidate_only
from app.main import init_app
from app.schema.ai_text_assist import AITextAssistAction, AITextAssistResponse

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


@pytest.fixture()
def client():
    app = init_app()

    async def fake_candidate_only():
        return CANDIDATE_PAYLOAD

    app.dependency_overrides[candidate_only] = fake_candidate_only
    return TestClient(app)


def test_improve_writing_success_returns_response_envelope(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_text_assist.AITextAssistService.assist",
        new=AsyncMock(
            return_value=AITextAssistResponse(
                text="Led a 5-engineer team to deliver a payments API.",
                action=AITextAssistAction.IMPROVE,
            )
        ),
    ) as mock_assist:
        response = client.post(
            "/candidate/resume/ai-text-assist",
            json={
                "text": "was responsible for a payments api",
                "action": "improve",
                "field_label": "Experience Description",
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Text improve applied successfully"
    assert body["data"] == {
        "text": "Led a 5-engineer team to deliver a payments API.",
        "action": "improve",
    }
    mock_assist.assert_awaited_once()
    (request_arg,), _ = mock_assist.call_args
    assert request_arg.text == "was responsible for a payments api"
    assert request_arg.field_label == "Experience Description"


@pytest.mark.parametrize("action", ["improve", "grammar", "shorter"])
def test_each_action_is_accepted(client, action):
    with patch(
        "app.controller.candidate_controller.candidate_ai_text_assist.AITextAssistService.assist",
        new=AsyncMock(
            return_value=AITextAssistResponse(text="Result text.", action=AITextAssistAction(action))
        ),
    ):
        response = client.post(
            "/candidate/resume/ai-text-assist",
            json={"text": "some current field text", "action": action},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["action"] == action


def test_works_without_field_label_for_any_description_field(client):
    with patch(
        "app.controller.candidate_controller.candidate_ai_text_assist.AITextAssistService.assist",
        new=AsyncMock(return_value=AITextAssistResponse(text="Shorter text.", action=AITextAssistAction.SHORTER)),
    ) as mock_assist:
        response = client.post(
            "/candidate/resume/ai-text-assist",
            json={"text": "Some long project description text.", "action": "shorter"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    (request_arg,), _ = mock_assist.call_args
    assert request_arg.field_label is None


def test_rejects_blank_text(client):
    response = client.post(
        "/candidate/resume/ai-text-assist",
        json={"text": "   ", "action": "improve"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 422


def test_requires_valid_action(client):
    response = client.post(
        "/candidate/resume/ai-text-assist",
        json={"text": "some text", "action": "not-a-real-action"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 422


def test_requires_candidate_role():
    app = init_app()

    from fastapi import HTTPException

    async def fake_forbidden():
        raise HTTPException(status_code=403, detail="Only candidates can access this resource")

    app.dependency_overrides[candidate_only] = fake_forbidden
    client = TestClient(app)

    response = client.post(
        "/candidate/resume/ai-text-assist",
        json={"text": "some text", "action": "improve"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 403


def test_service_unavailable_propagates_503(client):
    from fastapi import HTTPException

    with patch(
        "app.controller.candidate_controller.candidate_ai_text_assist.AITextAssistService.assist",
        new=AsyncMock(side_effect=HTTPException(status_code=503, detail="The AI writer is temporarily unavailable.")),
    ):
        response = client.post(
            "/candidate/resume/ai-text-assist",
            json={"text": "some text", "action": "improve"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 503
    