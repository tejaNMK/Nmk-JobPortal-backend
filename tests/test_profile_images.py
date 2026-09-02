import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.controller.profile_images import router as profile_images_router
from app.schema.shortlisted_candidates import ShortlistedCandidateFilterParams
from app.service import s3_service
from app.service.employer_service.shortlisted_candidates_service import (
    ShortlistedCandidatesService,
)
from app.utils.image_urls import resolve_profile_image_url


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(profile_images_router)
    return TestClient(app)


def test_profile_image_redirect_uses_expected_s3_key():
    user_id = "7fcb3e90-d3f5-4f26-92a9-154e96adf166"
    seen_keys = []

    def object_exists(key):
        seen_keys.append(key)
        return True

    def presign(key, expiry_seconds=300):
        seen_keys.append(key)
        assert expiry_seconds == 300
        return "https://signed.example/profile.jpg?X-Amz-Signature=abc"

    with patch.object(s3_service, "object_exists", side_effect=object_exists), patch.object(
        s3_service,
        "generate_profile_image_presigned_url",
        side_effect=presign,
    ):
        response = _client().get(
            f"/profile-images/{user_id}/profile.jpg",
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "https://signed.example/profile.jpg?X-Amz-Signature=abc"
    assert response.headers["cache-control"] == "private, max-age=300"
    assert seen_keys == [
        f"profile-images/{user_id}/profile.jpg",
        f"profile-images/{user_id}/profile.jpg",
    ]


def test_profile_image_missing_returns_404():
    user_id = "7fcb3e90-d3f5-4f26-92a9-154e96adf166"
    with patch.object(s3_service, "object_exists", return_value=False):
        response = _client().get(f"/profile-images/{user_id}/profile.jpg")

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile image not found"


def test_profile_image_invalid_user_id_is_rejected():
    response = _client().get("/profile-images/not-a-uuid/profile.jpg")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid user ID"


@pytest.mark.parametrize("filename", ["..", "..jpg", "profile/secret.jpg", "profile%2Fsecret.jpg"])
def test_profile_image_path_traversal_is_rejected(filename):
    user_id = "7fcb3e90-d3f5-4f26-92a9-154e96adf166"
    response = _client().get(f"/profile-images/{user_id}/{filename}")

    assert response.status_code in {400, 404}
    assert "AWS" not in response.text
    assert "S3_BUCKET_NAME" not in response.text


def test_profile_image_s3_failure_is_sanitized():
    user_id = "7fcb3e90-d3f5-4f26-92a9-154e96adf166"
    with patch.object(
        s3_service,
        "object_exists",
        side_effect=HTTPException(
            status_code=503,
            detail="File storage is unavailable",
        ),
    ):
        response = _client().get(f"/profile-images/{user_id}/profile.jpg")

    assert response.status_code == 503
    assert response.json()["detail"] == "File storage is unavailable"
    assert "SECRET" not in response.text
    assert "test-bucket" not in response.text
    assert "profile-images/" not in response.text


def test_resolve_profile_image_url_keeps_https_urls_and_empty_values():
    assert resolve_profile_image_url("https://cdn.example/avatar.jpg") == "https://cdn.example/avatar.jpg"
    assert resolve_profile_image_url(None) is None
    assert resolve_profile_image_url("") is None
    assert resolve_profile_image_url("   ") is None


def test_resolve_profile_image_url_converts_raw_profile_image_key():
    user_id = "7fcb3e90-d3f5-4f26-92a9-154e96adf166"

    assert (
        resolve_profile_image_url(f"profile-images/{user_id}/profile.jpg")
        == f"/profile-images/{user_id}/profile.jpg"
    )


def test_resolve_profile_image_url_never_falls_back_to_raw_key_on_failure():
    raw_key = "profile-images/7fcb3e90-d3f5-4f26-92a9-154e96adf166/profile.jpg"
    with patch.object(s3_service, "build_profile_image_key", side_effect=RuntimeError("SECRET internal S3 error")):
        assert resolve_profile_image_url(raw_key) is None


def test_shortlisted_candidate_list_returns_usable_image_url():
    candidate_user_id = "7fcb3e90-d3f5-4f26-92a9-154e96adf166"
    row = (
        SimpleNamespace(
            application_id="app-1",
            job_id="job-1",
            candidate_id="candidate-1",
            referral_contact=None,
            source=None,
            applied_at=datetime(2026, 8, 1, 10, 0, 0),
            updated_at=datetime(2026, 8, 2, 10, 0, 0),
            application_status="SHORTLISTED",
            candidate_rating=None,
            shortlisted_at=datetime(2026, 8, 2, 10, 0, 0),
        ),
        SimpleNamespace(candidate_id="candidate-1"),
        SimpleNamespace(
            first_name="Alice",
            last_name="Example",
            email="alice@example.com",
            mobile_number="9999999999",
            profile_image_url=f"profile-images/{candidate_user_id}/profile.jpg",
        ),
        None,
        SimpleNamespace(title="Backend Engineer"),
    )

    with patch(
        "app.service.employer_service.shortlisted_candidates_service."
        "ShortlistedCandidatesRepo.get_employer_id",
        new_callable=AsyncMock,
        return_value="emp-1",
    ), patch(
        "app.service.employer_service.shortlisted_candidates_service."
        "ShortlistedCandidatesRepo.get_shortlisted_candidates",
        new_callable=AsyncMock,
        return_value=(1, [row]),
    ):
        result = asyncio.run(
            ShortlistedCandidatesService.list_shortlisted_candidates(
                session=SimpleNamespace(),
                user_id=uuid4(),
                filters=ShortlistedCandidateFilterParams(),
            )
        )

    assert (
        result.items[0].profile_image_url
        == f"/profile-images/{candidate_user_id}/profile.jpg"
    )
