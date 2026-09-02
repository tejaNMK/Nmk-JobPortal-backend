from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.candidate_schema import ResumeShareLinkCreateSchema
from app.config import get_db
from app.controller.candidate_controller.candidate import router
from app.exception_handlers import register_exception_handlers
from app.repository.candidate_repo import CandidateProfileRepo
from app.service import candidate_service
from app.service.candidate_service import CandidateProfileService


class FakeSession:
    async def execute(self, *args, **kwargs):
        return None


@pytest.fixture()
def public_client():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


def _shared_resume(*, expires_at, token="valid-token"):
    return SimpleNamespace(
        resume_id="resume-1",
        candidate_id="candidate-1",
        file_name="resume.pdf",
        template="Minimal ATS",
        blob_ref="resumes/resume.pdf",
        share_token=token,
        share_enabled=True,
        share_requires_email=True,
        share_expires_at=expires_at,
        share_view_count=0,
        is_archived=False,
    )


@pytest.mark.asyncio
async def test_create_share_link_default_expiry_is_thirty_days(monkeypatch):
    created_at = datetime(2026, 8, 18, 10, 30, 0)
    resume = _shared_resume(expires_at=created_at + timedelta(days=30))
    captured = {}

    async def set_share_link(**kwargs):
        captured.update(kwargs)
        return resume

    monkeypatch.setattr(candidate_service, "utc_now_naive", lambda: created_at)
    monkeypatch.setattr(candidate_service, "_get_profile_or_404", AsyncMock(return_value=SimpleNamespace(candidate_id="candidate-1")))
    monkeypatch.setattr(CandidateProfileRepo, "set_resume_share_link", set_share_link)

    result = await CandidateProfileService.create_resume_share_link(
        FakeSession(), uuid4(), "resume-1", ResumeShareLinkCreateSchema()
    )

    assert captured["expires_at"] == created_at + timedelta(days=30)
    assert result.share_expires_at == created_at + timedelta(days=30)


@pytest.mark.asyncio
async def test_create_share_link_honours_custom_expiry_days(monkeypatch):
    created_at = datetime(2026, 8, 18, 10, 30, 0)
    captured = {}

    async def set_share_link(**kwargs):
        captured.update(kwargs)
        return _shared_resume(expires_at=kwargs["expires_at"])

    monkeypatch.setattr(candidate_service, "utc_now_naive", lambda: created_at)
    monkeypatch.setattr(candidate_service, "_get_profile_or_404", AsyncMock(return_value=SimpleNamespace(candidate_id="candidate-1")))
    monkeypatch.setattr(CandidateProfileRepo, "set_resume_share_link", set_share_link)

    await CandidateProfileService.create_resume_share_link(
        FakeSession(), uuid4(), "resume-1", ResumeShareLinkCreateSchema(expires_in_days=7)
    )

    assert captured["expires_at"] == created_at + timedelta(days=7)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current_time", "is_expired"),
    [
        (datetime(2026, 9, 17, 10, 29, 59), False),
        (datetime(2026, 9, 17, 10, 30, 0), True),
        (datetime(2026, 9, 18, 10, 30, 0), True),
    ],
    ids=["before-expiry", "at-expiry", "after-31-days"],
)
async def test_shared_resume_expiry_boundary(monkeypatch, current_time, is_expired):
    expires_at = datetime(2026, 9, 17, 10, 30, 0)
    monkeypatch.setattr(candidate_service, "utc_now_naive", lambda: current_time)
    monkeypatch.setattr(CandidateProfileRepo, "get_resume_by_share_token", AsyncMock(return_value=_shared_resume(expires_at=expires_at)))

    if is_expired:
        with pytest.raises(HTTPException, match="This link has expired") as exc_info:
            await CandidateProfileService._resolve_shared_resume(FakeSession(), "valid-token")
        assert exc_info.value.status_code == 404
    else:
        resolved = await CandidateProfileService._resolve_shared_resume(FakeSession(), "valid-token")
        assert resolved.share_token == "valid-token"


@pytest.mark.asyncio
async def test_access_shared_resume_before_expiry_succeeds(monkeypatch):
    expires_at = datetime(2026, 9, 17, 10, 30, 0)
    monkeypatch.setattr(candidate_service, "utc_now_naive", lambda: expires_at - timedelta(seconds=1))
    monkeypatch.setattr(CandidateProfileRepo, "get_resume_by_share_token", AsyncMock(return_value=_shared_resume(expires_at=expires_at)))
    monkeypatch.setattr(CandidateProfileRepo, "increment_resume_share_view_count", AsyncMock())
    monkeypatch.setattr(candidate_service.s3_service, "generate_presigned_url", lambda *args, **kwargs: "https://download.example/resume")

    result = await CandidateProfileService.access_shared_resume(FakeSession(), "valid-token", "reader@example.com")

    assert result.download_url == "https://download.example/resume"


def test_expired_share_link_returns_expected_http_error(public_client, monkeypatch):
    expires_at = datetime(2026, 9, 17, 10, 30, 0)
    monkeypatch.setattr(candidate_service, "utc_now_naive", lambda: expires_at)
    monkeypatch.setattr(CandidateProfileRepo, "get_resume_by_share_token", AsyncMock(return_value=_shared_resume(expires_at=expires_at)))

    response = public_client.post(
        "/candidate/public/resume/valid-token/access",
        json={"email": "reader@example.com"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "status": 404,
        "message": "This link has expired",
        "error": {"code": "NOT_FOUND", "details": "This link has expired"},
    }


def test_nonexistent_share_token_remains_invalid(public_client, monkeypatch):
    monkeypatch.setattr(CandidateProfileRepo, "get_resume_by_share_token", AsyncMock(return_value=None))

    response = public_client.get("/candidate/public/resume/missing-token")

    assert response.status_code == 404
    assert response.json()["message"] == "This link is invalid or no longer available"
