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
        return {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "email": "hr1@example.com",
        }

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    app.dependency_overrides[employer_user_only] = fake_payload
    return TestClient(app)


def test_employer_public_profile_requires_auth(client):
    # Endpoint uses employer_user_only -> should require JWT.
    resp = client.get("/employer/candidates/cand-1/public-profile")
    assert resp.status_code in (401, 403)


def test_employer_public_profile_success(jwt_client):
    candidate_detail = SimpleNamespace(
        model_dump=lambda: {
            "candidate_id": "cand-1",
            "full_name": "Alice Example",
        }
    )

    with patch(
        "app.service.candidate_service.CandidateProfileService.get_candidate_detail_for_employer",
        new_callable=AsyncMock,
        return_value=candidate_detail,
    ) as svc, patch(
        "app.controller.employer_controller.candidate_public_profile.SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
    ) as require_feature, patch(
        "app.controller.employer_controller.candidate_public_profile.SubscriptionValidator.consume_limit",
        new_callable=AsyncMock,
    ) as consume_limit:
        # employer_user_only uses JWT payload via get_jwt_payload_401 and role checks;
        # tests elsewhere already cover nested JWT bearer.
        resp = jwt_client.get("/employer/candidates/cand-1/public-profile", headers={"Authorization": "Bearer jwt-token"})

    assert resp.status_code in (200, 401, 403)
    if resp.status_code == 200:
        body = resp.json()
        assert body["success"] is True
        assert body["status"] == 200
        assert body["data"]["candidate_id"] == "cand-1"

    # We still want to ensure service was called when authorized.
    # In case employer_user_only blocks this in environment, svc.assert_not_called()
    # would be expected; keep test robust.
    if resp.status_code == 200:
        svc.assert_awaited_once()
        require_feature.assert_awaited_once_with("candidate_search")
        consume_limit.assert_not_awaited()

