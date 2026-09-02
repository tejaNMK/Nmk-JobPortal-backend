from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app


class FakeSession:
    pass


@pytest.fixture()
def client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "email": "user@example.com",
        }
    
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
    return TestClient(app)


def test_get_user_profile_success(jwt_client):
    with patch(
        "app.controller.authentication.users.UserService.get_user_profile",
        new_callable=AsyncMock,
        return_value={
            "email": "user@example.com",
            "first_name": "Sai",
        },
    ) as service:

        response = jwt_client.get(
            "/users/",
            headers={"Authorization": "Bearer jwt-token"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Successfully fetched user profile"
    assert response.json()["data"]["email"] == "user@example.com"

    service.assert_awaited_once()

def test_get_user_profile_requires_auth(client):
    response = client.get("/users/")
    assert response.status_code in (401, 403)


def test_forgot_userid_success(client):
    with patch(
        "app.controller.authentication.authentication.AuthService.forgot_userid_service",
        new_callable=AsyncMock,
        return_value={"delivery_channel": "email"},
    ) as service:
        response = client.post("/auth/forgot-userid", json={"email": "user@example.com"})

    assert response.status_code == 200
    assert response.json()["message"] == "User ID retrieval initiated"
    assert response.json()["data"] == {"delivery_channel": "email"}
    service.assert_awaited_once()

def test_forgot_userid_requires_contact(client):
    response = client.post("/auth/forgot-userid", json={})
    assert response.status_code == 422



@pytest.mark.parametrize(
    "path,service_name,expected_detail",
    [
        ("/auth/signout", "signout_service", "Signed out successfully"),
        (
            "/auth/signout-all",
            "signout_all_service",
            "All sessions signed out successfully",
        ),
    ],
)
def test_signout_endpoints_success(
    client,
    path,
    service_name,
    expected_detail,
):
    with patch(
        "app.repository.authentication.auth_repo.JWTBearer.verify_jwt",
        new_callable=AsyncMock,
        return_value=True,
    ), patch(
        f"app.controller.authentication.authentication.AuthService.{service_name}",
        new_callable=AsyncMock,
        return_value={"message": expected_detail},
    ) as service:

        response = client.post(
            path,
            headers={
                "Authorization": "Bearer jwt-token"
            }
        )
        print("\nSTATUS:", response.status_code)
        print("BODY:", response.json())

    assert response.status_code == 200
    assert response.json()["message"] == expected_detail

    service.assert_awaited_once()


@pytest.mark.parametrize("path", ["/auth/signout", "/auth/signout-all"])
def test_signout_endpoints_require_auth(client, path):
    response = client.post(path)
    assert response.status_code in (401, 403)


def _job_obj(**overrides):
    data = {
        "job_id": "job-1",
        "employer_id": "employer-1",
        "title": "Python Backend Developer",
        "description": "Build APIs",
        "employment_type": "FULL_TIME",
        "experience_min": 2,
        "experience_max": 5,
        "location": "Hyderabad",
        "work_mode": "REMOTE",
        "skills": ["Python", "FastAPI"],
        "salary_min": 800000.0,
        "salary_max": 1200000.0,
        "no_of_openings": 2,
        "application_deadline": None,
        "company_name": "NMK Technologies",
        "contact_email": "hr@nmktechnologies.com",
        "status": "PUBLISHED",
        "created_at": None,
        "updated_at": None,
        "created_by": "user-1",
        "updated_by": "user-1",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


VALID_JOB_BODY = {
    "job_title": "Python Backend Developer",
    "job_description": "Build APIs",
    "employment_type": "Full Time",
    "experience_required": "2-5",
    "location": "Hyderabad",
    "work_mode": "remote",
    "skills": ["Python", "FastAPI"],
    "salary_range": "800000-1200000",
    "number_of_openings": 2,
    "application_deadline": "2099-12-31T23:59:59+00:00",
    "company_name": "NMK Technologies",
    "contact_email": "hr@nmktechnologies.com",
    "status": "published",
}


def test_post_job_success(jwt_client):
    employer = SimpleNamespace(id="employer-1")

    with patch(
        "app.controller.employer_controller.job._get_or_create_employer_profile",
        new_callable=AsyncMock,
        return_value=employer,
    ), patch(
        "app.controller.employer_controller.job.JobService.create_post_job",
        new_callable=AsyncMock,
        return_value=_job_obj(),
    ) as service:
        response = jwt_client.post("/jobs/", json=VALID_JOB_BODY)

    assert response.status_code == 201
    assert response.json()["message"] == "Job created successfully"
    assert response.json()["data"]["job_title"] == "Python Backend Developer"
    assert response.json()["data"]["employment_type"] == "FULL_TIME"
    service.assert_awaited_once()


def test_post_job_rejects_invalid_payload(jwt_client):
    invalid = {**VALID_JOB_BODY, "number_of_openings": 0}
    response = jwt_client.post("/jobs/", json=invalid)
    assert response.status_code == 422


def test_post_job_rejects_empty_idempotency_key(jwt_client):
    response = jwt_client.post(
        "/jobs/",
        json=VALID_JOB_BODY,
        headers={"Idempotency-Key": " "},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
    assert response.json()["message"] == "Idempotency-Key cannot be empty"


def test_post_job_propagates_authorization_error(jwt_client):
    employer = SimpleNamespace(id="employer-1")

    with patch(
        "app.controller.employer_controller.job._get_or_create_employer_profile",
        new_callable=AsyncMock,
        return_value=employer,
    ), patch(
        "app.controller.employer_controller.job.JobService.create_post_job",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=403, detail="Only employers can create jobs"),
    ):
        response = jwt_client.post("/jobs/", json=VALID_JOB_BODY)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert response.json()["message"] == "Only employers can create jobs"
