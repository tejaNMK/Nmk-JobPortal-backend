from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import init_app
from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401


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
        return {"user_id": "22222222-2222-2222-2222-222222222222"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    return TestClient(app)


def test_candidate_invitations_list_requires_auth(client):
    resp = client.get("/candidate/invitations")
    assert resp.status_code in (401, 403)


def test_candidate_invitations_list_success(jwt_client):
    fake_result = SimpleNamespace(
        model_dump=lambda: {
            "page": 1,
            "page_size": 20,
            "total_records": 1,
            "items": [
                {
                    "invitation_id": "inv-1",
                    "company_name": "Acme Corp",
                    "company_logo": None,
                    "employer_name": "Acme Corp",
                    "job_title": "Software Engineer",
                    "job_location": "Remote",
                    "employment_type": "Full-time",
                    "invitation_message": "Join us",
                    "invited_at": None,
                    "status": "PENDING",
                }
            ],
        }
    )

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService.list_invitations",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as svc:
        resp = jwt_client.get(
            "/candidate/invitations",
            headers={"Authorization": "Bearer jwt-token"},
            params={"page": 1, "page_size": 20, "sort_by": "newest", "status": "PENDING"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == 200
    assert body["data"]["total_records"] == 1
    svc.assert_awaited_once()


def test_candidate_invitation_details_success(jwt_client):
    fake_result = SimpleNamespace(
        model_dump=lambda: {
            "invitation_id": "inv-1",
            "status": "PENDING",
            "invitation_message": "Join us",
            "employer": {"employer_id": "emp-1", "company_name": "Acme Corp"},
            "company": {"employer_id": "emp-1", "company_name": "Acme Corp"},
            "recruiter": {"full_name": "Recruiter One"},
            "job": {
                "job_id": "job-1",
                "job_title": "Software Engineer",
                "skills": ["Python"],
            },
            "job_details_url": "/candidate/jobs/job-1",
        }
    )

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService.get_invitation_details",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as svc:
        resp = jwt_client.get(
            "/candidate/invitations/inv-1",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["invitation_id"] == "inv-1"
    assert body["data"]["job"]["job_id"] == "job-1"
    svc.assert_awaited_once()


def test_candidate_invitation_accept_success(jwt_client):
    fake_result = SimpleNamespace(
        model_dump=lambda: {
            "invitation_id": "inv-1",
            "status": "ACCEPTED",
            "job_id": "job-1",
            "job_details_url": "/candidate/jobs/job-1",
        }
    )

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService.accept_invitation",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as svc:
        resp = jwt_client.post(
            "/candidate/invitations/inv-1/accept",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ACCEPTED"
    assert body["data"]["job_id"] == "job-1"
    svc.assert_awaited_once()


def test_candidate_invitation_reject_success(jwt_client):
    fake_result = SimpleNamespace(
        model_dump=lambda: {
            "invitation_id": "inv-1",
            "status": "REJECTED",
            "job_id": "job-1",
            "job_details_url": "/candidate/jobs/job-1",
        }
    )

    with patch(
        "app.service.employer_service.invitations_service.CandidateInvitationsService.reject_invitation",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as svc:
        resp = jwt_client.post(
            "/candidate/invitations/inv-1/reject",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "REJECTED"
    svc.assert_awaited_once()

