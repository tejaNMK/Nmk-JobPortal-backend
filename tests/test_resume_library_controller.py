from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app


USER_ID = uuid4()


class DumpableResult:
    """Mimics a pydantic response model well enough for `.model_dump()`."""

    def __init__(self, **data):
        self.data = data

    def model_dump(self):
        return self.data


class FakeSession:
    async def execute(self, *args, **kwargs):
        return None

    async def commit(self):
        return None

    async def flush(self):
        return None

    def add(self, obj):
        pass


@pytest.fixture()
def auth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {"user_id": str(USER_ID), "email": "candidate@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    return TestClient(app)


def _resume_payload(**overrides):
    base = dict(
        resume_id="resume-1",
        file_name="resume.pdf",
        version_name="General Product Resume",
        template="Minimal ATS",
        notes="Primary resume",
        usage_note="Used in 8 applications",
        is_active=True,
        is_archived=False,
        download_count=4,
        share_enabled=False,
        share_requires_email=False,
        share_view_count=0,
    )
    base.update(overrides)
    return base


def test_update_resume_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.update_resume",
        new_callable=AsyncMock,
        return_value=DumpableResult(**_resume_payload(version_name="Renamed Resume")),
    ) as service:
        response = auth_client.patch(
            "/candidate/profile/resumes/resume-1",
            json={"version_name": "Renamed Resume"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Resume updated successfully"
    assert body["data"]["version_name"] == "Renamed Resume"
    service.assert_awaited_once()


def test_update_resume_requires_at_least_one_field(auth_client):
    response = auth_client.patch("/candidate/profile/resumes/resume-1", json={})
    assert response.status_code == 422


def test_archive_resume_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.set_resume_archived",
        new_callable=AsyncMock,
        return_value=DumpableResult(**_resume_payload(is_archived=True, is_active=False)),
    ) as service:
        response = auth_client.patch("/candidate/profile/resumes/resume-1/archive")

    assert response.status_code == 200
    assert response.json()["data"]["is_archived"] is True
    service.assert_awaited_once()


def test_restore_resume_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.set_resume_archived",
        new_callable=AsyncMock,
        return_value=DumpableResult(**_resume_payload(is_archived=False)),
    ) as service:
        response = auth_client.patch("/candidate/profile/resumes/resume-1/restore")

    assert response.status_code == 200
    assert response.json()["data"]["is_archived"] is False
    service.assert_awaited_once()


def test_duplicate_resume_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.duplicate_resume",
        new_callable=AsyncMock,
        return_value=DumpableResult(**_resume_payload(resume_id="resume-2", version_name="General Product Resume (Copy)", is_active=False)),
    ) as service:
        response = auth_client.post("/candidate/profile/resumes/resume-1/duplicate")

    assert response.status_code == 201
    assert response.json()["data"]["version_name"] == "General Product Resume (Copy)"
    service.assert_awaited_once()


def test_create_resume_share_link_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.create_resume_share_link",
        new_callable=AsyncMock,
        return_value=DumpableResult(
            resume_id="resume-1",
            share_token="abc123",
            share_enabled=True,
            share_requires_email=False,
            share_view_count=0,
            share_url="https://jobsportal.com/cv/abc123",
        ),
    ) as service:
        response = auth_client.post(
            "/candidate/profile/resumes/resume-1/share",
            json={"requires_email": False, "expires_in_days": 30},
        )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["share_enabled"] is True
    assert body["share_url"] == "https://jobsportal.com/cv/abc123"
    service.assert_awaited_once()


def test_disable_resume_share_link_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.disable_resume_share_link",
        new_callable=AsyncMock,
        return_value=DumpableResult(resume_id="resume-1", share_token="abc123", share_enabled=False),
    ) as service:
        response = auth_client.patch("/candidate/profile/resumes/resume-1/share/disable")

    assert response.status_code == 200
    assert response.json()["data"]["share_enabled"] is False
    # token is preserved so the link can be re-enabled later
    assert response.json()["data"]["share_token"] == "abc123"
    service.assert_awaited_once()


def test_enable_resume_share_link_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.enable_resume_share_link",
        new_callable=AsyncMock,
        return_value=DumpableResult(
            resume_id="resume-1",
            share_token="abc123",
            share_enabled=True,
            share_url="https://jobsportal.com/cv/abc123",
        ),
    ) as service:
        response = auth_client.patch("/candidate/profile/resumes/resume-1/share/enable")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["share_enabled"] is True
    # re-enabling reuses the same URL that was previously disabled
    assert body["share_url"] == "https://jobsportal.com/cv/abc123"
    service.assert_awaited_once()


def test_delete_resume_share_link_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.delete_resume_share_link",
        new_callable=AsyncMock,
        return_value=DumpableResult(resume_id="resume-1", share_token=None, share_enabled=False, share_url=None),
    ) as service:
        response = auth_client.delete("/candidate/profile/resumes/resume-1/share")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["share_enabled"] is False
    assert body["share_token"] is None
    service.assert_awaited_once()


def test_generate_resume_pdf_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.generate_resume_pdf",
        new_callable=AsyncMock,
        return_value=(b"%PDF-1.4 fake pdf bytes", "resume-ats.pdf"),
    ) as service:
        response = auth_client.get("/candidate/profile/resume/generate", params={"style": "ats"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 fake pdf bytes"
    assert "resume-ats.pdf" in response.headers["content-disposition"]
    service.assert_awaited_once()


def test_generate_resume_pdf_rejects_invalid_style(auth_client):
    response = auth_client.get("/candidate/profile/resume/generate", params={"style": "flashy"})
    assert response.status_code == 422