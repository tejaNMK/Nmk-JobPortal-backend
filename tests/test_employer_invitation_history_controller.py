from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import init_app
from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.dependencies.role_dependencies import employer_user_only


class FakeSession:
    pass


@pytest.fixture()
def client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


@pytest.fixture()
def jwt_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {"user_id": "11111111-1111-1111-1111-111111111111", "email": "hr1@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    app.dependency_overrides[employer_user_only] = fake_payload
    return TestClient(app)


def test_employer_invitation_history_requires_auth(client):
    resp = client.get("/employer/invitations")
    assert resp.status_code in (401, 403)


def test_employer_invitation_history_success(jwt_client):
    fake_result = SimpleNamespace(
        model_dump=lambda: {
            "page": 1,
            "page_size": 20,
            "total_records": 1,
            "items": [
                {
                    "invitation_id": "inv-1",
                    "candidate": {
                        "candidate_id": "cand-1",
                        "full_name": "Alice Example",
                        "profile_photo": None,
                        "profile_headline": None,
                        "current_designation": None,
                        "years_of_experience": None,
                        "location": None,
                        "top_skills": [],
                        "education_summary": None,
                        "availability": None,
                        "profile_completion_percentage": None,
                        "last_updated": None,
                    },
                    "job_title": None,
                    "status": "PENDING",
                    "invited_at": None,
                    "viewed_at": None,
                    "responded_at": None,
                }
            ],
        }
    )

    with patch(
        "app.service.employer_service.invitations_service.EmployerInvitationsService.list_invitations",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as svc:
        resp = jwt_client.get(
            "/employer/invitations",
            headers={"Authorization": "Bearer jwt-token"},
            params={"page": 1, "page_size": 20, "sort_by": "newest"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == 200
    assert body["data"]["total_records"] == 1
    svc.assert_awaited_once()

