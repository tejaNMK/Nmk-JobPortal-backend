from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app


CANDIDATE_USER_ID = uuid4()
EMPLOYER_USER_ID = uuid4()


class DumpableResult:
    def __init__(self, **data):
        self.data = data

    def model_dump(self):
        return self.data


class FakeSession:
    pass


def _fake_user(role_code: str, user_id):
    return SimpleNamespace(
        user_id=user_id,
        roles=[SimpleNamespace(role_code=role_code)],
    )


@pytest.fixture()
def auth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {"user_id": str(CANDIDATE_USER_ID), "email": "candidate@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload

    patcher = patch(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_fake_user("ROLE_CANDIDATE", CANDIDATE_USER_ID),
    )
    patcher.start()

    client = TestClient(app)
    client._role_patcher = patcher
    return client


@pytest.fixture()
def employer_auth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {"user_id": str(EMPLOYER_USER_ID), "email": "employer@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload

    patcher = patch(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_fake_user("ROLE_EMPLOYER", EMPLOYER_USER_ID),
    )
    patcher.start()

    client = TestClient(app)
    client._role_patcher = patcher
    return client


@pytest.fixture()
def unauth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


def test_list_followings_requires_auth(unauth_client):
    response = unauth_client.get("/candidate/followings")
    assert response.status_code == 401


def test_employer_cannot_access_followings(employer_auth_client):
    response = employer_auth_client.get("/candidate/followings")
    assert response.status_code == 403


def test_list_followings_success(auth_client):
    fake_result = DumpableResult(
        items=[
            {
                "company_id": "co-1",
                "name": "Skyline Digital",
                "industry": "Product & Engineering",
                "location": "San Francisco",
                "logo": None,
                "open_jobs_count": 3,
                "followed_at": "2026-07-01T00:00:00",
            }
        ],
        total=1,
        page=1,
        page_size=20,
        notify_enabled=False,
    )
    with patch(
        "app.controller.candidate_controller.candidate_followings.CandidateFollowingService.list_followings",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.get("/candidate/followings", params={"search": "Skyline"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["name"] == "Skyline Digital"
    service.assert_awaited_once()


def test_follow_company_success(auth_client):
    fake_result = DumpableResult(
        message="Company followed successfully",
        company_id="co-1",
        is_following=True,
    )
    with patch(
        "app.controller.candidate_controller.candidate_followings.CandidateFollowingService.follow_company",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(message="Company followed successfully", model_dump=fake_result.model_dump),
    ) as service:
        response = auth_client.post("/candidate/followings/co-1")

    assert response.status_code == 201
    assert response.json()["message"] == "Company followed successfully"
    assert response.json()["data"]["is_following"] is True
    service.assert_awaited_once()


def test_follow_company_not_found(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate_followings.CandidateFollowingService.follow_company",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Company not found"),
    ):
        response = auth_client.post("/candidate/followings/missing-co")

    assert response.status_code == 404
    assert response.json()["message"] == "Company not found"


def test_unfollow_company_success(auth_client):
    fake_result = SimpleNamespace(
        message="Company unfollowed successfully",
        model_dump=lambda: {
            "message": "Company unfollowed successfully",
            "company_id": "co-1",
            "is_following": False,
        },
    )
    with patch(
        "app.controller.candidate_controller.candidate_followings.CandidateFollowingService.unfollow_company",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.delete("/candidate/followings/co-1")

    assert response.status_code == 200
    assert response.json()["data"]["is_following"] is False
    service.assert_awaited_once()


def test_unfollow_company_not_following(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate_followings.CandidateFollowingService.unfollow_company",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="You are not following this company"),
    ):
        response = auth_client.delete("/candidate/followings/co-1")

    assert response.status_code == 404


def test_bulk_follow_success(auth_client):
    fake_result = SimpleNamespace(
        model_dump=lambda: {
            "followed": ["co-1", "co-2"],
            "already_following": ["co-3"],
            "not_found": ["co-4"],
        }
    )
    with patch(
        "app.controller.candidate_controller.candidate_followings.CandidateFollowingService.bulk_follow",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.post(
            "/candidate/followings/bulk-follow",
            json={"company_ids": ["co-1", "co-2", "co-3", "co-4"]},
        )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["followed"] == ["co-1", "co-2"]
    assert body["already_following"] == ["co-3"]
    assert body["not_found"] == ["co-4"]
    service.assert_awaited_once()


def test_bulk_follow_requires_at_least_one_id(auth_client):
    response = auth_client.post("/candidate/followings/bulk-follow", json={"company_ids": []})
    assert response.status_code == 422


def test_smart_suggestions_success(auth_client):
    fake_result = SimpleNamespace(
        model_dump=lambda: {
            "groups": [
                {
                    "group_key": "hiring-for-role",
                    "title": "Companies hiring for Lead Product roles",
                    "subtitle": "Based on your saved jobs and search history.",
                    "action": "FOLLOW_ALL",
                    "companies": [
                        {
                            "company_id": "co-9",
                            "name": "NovaCloud",
                            "industry": "Cloud Infrastructure",
                            "location": "Austin",
                            "logo": None,
                        }
                    ],
                }
            ]
        }
    )
    with patch(
        "app.controller.candidate_controller.candidate_followings.CandidateFollowingService.get_smart_suggestions",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.get("/candidate/followings/suggestions")

    assert response.status_code == 200
    groups = response.json()["data"]["groups"]
    assert groups[0]["title"] == "Companies hiring for Lead Product roles"
    service.assert_awaited_once()


def test_update_notify_preference_success(auth_client):
    fake_result = SimpleNamespace(model_dump=lambda: {"notify_enabled": True})
    with patch(
        "app.controller.candidate_controller.candidate_followings.CandidateFollowingService.set_notify_preference",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as service:
        response = auth_client.patch(
            "/candidate/followings/notify-preference",
            json={"enabled": True},
        )

    assert response.status_code == 200
    assert response.json()["data"]["notify_enabled"] is True
    service.assert_awaited_once()


def test_update_notify_preference_validates_body(auth_client):
    response = auth_client.patch("/candidate/followings/notify-preference", json={})
    assert response.status_code == 422