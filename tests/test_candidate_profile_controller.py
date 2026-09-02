from io import BytesIO
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch
from uuid import uuid4

import pytest
from docx import Document
from fastapi import HTTPException
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app


USER_ID = uuid4()


def _make_pdf_bytes(text: str | None = "Jane Doe - Software Engineer") -> bytes:
    """Build a real, parseable PDF, optionally with a line of text on it."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    if text:
        pdf.drawString(72, 800, text)
    pdf.save()
    return buffer.getvalue()


def _make_docx_bytes(text: str | None = "Jane Doe - Software Engineer") -> bytes:
    """Build a real .docx file, optionally with a paragraph of text in it."""
    buffer = BytesIO()
    document = Document()
    if text:
        document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


class DumpableResult:
    def __init__(self, **data):
        self.data = data

    def model_dump(self):
        return self.data


class FakeResult:

    async def execute(self, *args, **kwargs):
        return FakeResult()

    async def commit(self):
        return None

    async def flush(self):
        return None

    def add(self, obj):
        if not getattr(obj, "resume_id", None):
            obj.resume_id = "resume-1"


@pytest.fixture()
def auth_client():
    app = init_app()

    async def fake_db():
        yield FakeResult()

    async def fake_payload():
        return {"user_id": str(USER_ID), "email": "candidate@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    return TestClient(app)


@pytest.fixture()
def unauth_client():
    app = init_app()

    async def fake_db():
        yield FakeResult()

    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


def test_candidate_dashboard_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateDashboardService.get_dashboard",
        new_callable=AsyncMock,
        return_value=DumpableResult(total_applications=3),
    ) as service:
        response = auth_client.get("/candidate/dashboard")

    assert response.status_code == 200
    assert response.json()["message"] == "Candidate dashboard fetched successfully"
    assert response.json()["data"] == {"total_applications": 3}
    service.assert_awaited_once()


def test_candidate_dashboard_requires_auth(unauth_client):
    response = unauth_client.get("/candidate/dashboard")
    assert response.status_code == 401


def test_candidate_profile_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.get_full_profile",
        new_callable=AsyncMock,
        return_value=DumpableResult(candidate_id="candidate-1"),
    ):
        response = auth_client.get("/candidate/profile")

    assert response.status_code == 200
    assert response.json()["data"] == {"candidate_id": "candidate-1"}


def test_candidate_listing_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.list_public_candidates",
        new_callable=AsyncMock,
        return_value=DumpableResult(total=1, page=1, page_size=20, items=[]),
    ) as service:
        response = auth_client.get("/candidates", params={"search": "python"})

    assert response.status_code == 200
    assert response.json()["message"] == "Candidates fetched successfully"
    assert response.json()["data"]["total"] == 1
    service.assert_awaited_once()


def test_candidate_detail_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.get_public_candidate_detail",
        new_callable=AsyncMock,
        return_value=DumpableResult(candidate_id="candidate-1", full_name="Sai Kiran"),
    ):
        response = auth_client.get("/candidates/candidate-1")

    assert response.status_code == 200
    assert response.json()["message"] == "Candidates fetched successfully"
    assert response.json()["data"]["candidate_id"] == "candidate-1"


@pytest.mark.parametrize(
    "method,path,body,service_name",
    [
        (
            "patch",
            "/candidate/profile/personal-info",
            {
                "first_name": "Sai",
                "last_name": "Kiran",
                "phone_number": "9876543210",
                "professional_title": "Lead Product Designer",
                "about_you": "Building delightful products.",
                "primary_location": "Seattle, USA",
                "preferred_locations": "Remote - San Francisco",
                "website": "https://www.personal-site.com",
                "portfolio_url": "https://dribbble.com/jordan",
            },
            "update_personal_info",
        ),
        (
            "patch",
            "/candidate/profile/social-links",
            {"linkedin_url": "https://linkedin.com/in/sai"},
            "update_social_links",
        ),
        (
            "post",
            "/candidate/profile/skills",
            {"name": "Python", "level": "Expert", "years": 5},
            "add_skill",
        ),
        (
            "post",
            "/candidate/profile/education",
            {
                "institution": "Stanford University",
                "degree": "BSc",
                "field_of_study": "Computer Science",
                "start_year": 2010,
                "graduation_year": 2014,
                "grade": "3.8 / 4.0",
            },
            "add_education",
        ),
        (
            "post",
            "/candidate/profile/experience",
            {
                "company": "Acme Corp",
                "role": "Senior Designer",
                "start_date": "2022-01-01",
                "end_date": "2024-12-01",
                "currently_working": False,
                "key_highlights": "Shipped 4 product lines.",
            },
            "add_experience",
        ),
        (
            "put",
            "/candidate/profile/certifications",
            {"certifications": [{"name": "AWS", "issuing_organization": "Amazon"}]},
            "update_certifications",
        ),
        (
            "post",
            "/candidate/profile/projects",
            {
                "title": "Resume Builder App",
                "technologies_used": "React, Node.js, PostgreSQL",
                "project_url": "https://github.com/sai/resume-builder",
                "description": "Built a resume builder used by 500 candidates.",
            },
            "add_project",
        ),
        (
            "patch",
            "/candidate/profile/visibility",
            {
                "profile_visibility": "public",
                "searchable_flag": True,
                "open_to_work": False,
                "search_engine_indexing": True,
            },
            "update_visibility",
        ),
        (
            "patch",
            "/candidate/profile/professional-snapshot",
            {"experience_level": "MID", "current_company": "NMK"},
            "update_professional_snapshot",
        ),
    ],
)
def test_candidate_profile_update_endpoints_success(auth_client, method, path, body, service_name):
    with patch(
        f"app.controller.candidate_controller.candidate.CandidateProfileService.{service_name}",
        new_callable=AsyncMock,
        return_value={"message": "Updated", "candidate_id": "candidate-1"},
    ) as service:
        response = getattr(auth_client, method)(path, json=body)

    assert response.status_code == 200
    assert response.json()["message"] == "Updated"
    assert response.json()["data"]["candidate_id"] == "candidate-1"
    service.assert_awaited_once()


def test_candidate_visibility_endpoint_accepts_open_to_work_false(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.update_visibility",
        new_callable=AsyncMock,
        return_value={
            "message": "Visibility settings updated successfully",
            "open_to_work": False,
        },
    ) as service:
        response = auth_client.patch("/candidate/profile/visibility", json={"open_to_work": False})

    assert response.status_code == 200
    assert response.json()["message"] == "Visibility settings updated successfully"
    assert response.json()["data"]["open_to_work"] is False
    body = service.await_args.args[2]
    assert body.open_to_work is False


def test_candidate_visibility_endpoint_accepts_search_engine_indexing(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.update_visibility",
        new_callable=AsyncMock,
        return_value={
            "message": "Visibility settings updated successfully",
            "search_engine_indexing": True,
        },
    ) as service:
        response = auth_client.patch(
            "/candidate/profile/visibility",
            json={"search_engine_indexing": True},
        )

    assert response.status_code == 200
    assert response.json()["data"]["search_engine_indexing"] is True
    body = service.await_args.args[2]
    assert body.search_engine_indexing is True


@pytest.mark.parametrize(
    "method,path,service_name",
    [
        ("patch", "/candidate/profile/skills/skill-1", "update_skill"),
        ("delete", "/candidate/profile/skills/skill-1", "delete_skill"),
        ("patch", "/candidate/profile/education/edu-1", "update_education"),
        ("delete", "/candidate/profile/education/edu-1", "delete_education"),
        ("patch", "/candidate/profile/experience/exp-1", "update_experience"),
        ("delete", "/candidate/profile/experience/exp-1", "delete_experience"),
        ("patch", "/candidate/profile/projects/proj-1", "update_project"),
        ("delete", "/candidate/profile/projects/proj-1", "delete_project"),
    ],
)
def test_candidate_profile_entry_crud_endpoints_success(auth_client, method, path, service_name):
    with patch(
        f"app.controller.candidate_controller.candidate.CandidateProfileService.{service_name}",
        new_callable=AsyncMock,
        return_value={"message": "Updated", "candidate_id": "candidate-1"},
    ) as service:
        kwargs = {"json": {}} if method == "patch" else {}
        response = getattr(auth_client, method)(path, **kwargs)

    assert response.status_code == 200
    assert response.json()["message"] == "Updated"
    service.assert_awaited_once()


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("patch", "/candidate/profile/personal-info", {"first_name": "S1", "last_name": "Kiran"}),
        ("patch", "/candidate/profile/social-links", {"github_url": "github.com/sai"}),
        ("post", "/candidate/profile/skills", {"name": "Python", "level": "Master"}),
        ("post", "/candidate/profile/education", {"degree": "B.Tech", "start_year": 2018}),
        (
            "post",
            "/candidate/profile/experience",
            {"company": "NMK", "role": "Dev", "start_date": "2022-01-01", "end_date": "2020-01-01"},
        ),
        (
            "put",
            "/candidate/profile/certifications",
            {"certifications": [{"name": "AWS", "issuing_organization": "Amazon", "credential_url": "amazon.com/cert"}]},
        ),
        ("post", "/candidate/profile/projects", {"technologies_used": "React"}),
        ("patch", "/candidate/profile/visibility", {"profile_visibility": "FRIENDS"}),
    ],
)
def test_candidate_profile_update_endpoints_validate_payload(auth_client, method, path, body):
    response = getattr(auth_client, method)(path, json=body)
    assert response.status_code == 422


def test_upload_resume_success(auth_client, tmp_path, monkeypatch):
    monkeypatch.setenv("RESUME_STORAGE_DIR", str(tmp_path))
    candidate = SimpleNamespace(candidate_id="candidate-1")

    with patch(
        "app.repository.candidate_repo.CandidateProfileRepo.get_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=candidate,
    ), patch(
        "app.repository.candidate_repo.CandidateProfileRepo.update_profile",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.repository.candidate_repo.CandidateProfileRepo.get_resumes",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.service.candidate_service.SubscriptionValidator.require_feature",
        new_callable=AsyncMock,
    ), patch(
        "app.service.candidate_service.SubscriptionValidator.get_limit",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.service.s3_service.upload_resume",
        return_value="resumes/candidate-1/resume.pdf",
    ):
        response = auth_client.post(
            "/candidate/profile/resume/upload",
            files={"file": ("resume.pdf", _make_pdf_bytes(), "application/pdf")},
        )

    assert response.status_code == 201
    assert response.json()["message"] == "Resume uploaded successfully"
    assert response.json()["data"]["file_name"] == "resume.pdf"


def test_upload_resume_rejects_invalid_file_type(auth_client):
    response = auth_client.post(
        "/candidate/profile/resume/upload",
        files={"file": ("resume.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert response.json()["message"] == "Only PDF and Word documents are allowed"


def test_upload_resume_rejects_mismatched_extension(auth_client):
    response = auth_client.post(
        "/candidate/profile/resume/upload",
        files={"file": ("resume.docx", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Resume file extension does not match the uploaded file type"


def test_upload_resume_rejects_large_file(auth_client):
    response = auth_client.post(
        "/candidate/profile/resume/upload",
        files={"file": ("resume.pdf", b"x" * (5 * 1024 * 1024 + 1), "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
    assert response.json()["message"] == "File size must not exceed 5 MB"


def test_upload_resume_rejects_empty_docx(auth_client):
    """QA bug: a .docx with no text/tables/images (e.g. a blank Word doc)
    passes the raw byte-size check since the zip container itself is several
    KB, but it isn't a usable resume and must be rejected."""
    response = auth_client.post(
        "/candidate/profile/resume/upload",
        files={
            "file": (
                "Empty file.docx",
                _make_docx_bytes(text=None),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "The selected file is empty. Please upload a resume with content."


def test_upload_resume_rejects_empty_pdf(auth_client):
    """Same scenario as the docx case, but for a PDF with a page and no text
    or images on it."""
    response = auth_client.post(
        "/candidate/profile/resume/upload",
        files={"file": ("resume.pdf", _make_pdf_bytes(text=None), "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "The selected file is empty. Please upload a resume with content."


def test_upload_resume_rejects_unreadable_docx(auth_client):
    """A file with a valid docx content-type/extension but bytes that aren't
    actually a docx (corrupted upload) should get a clear "couldn't read it"
    message rather than a 500 or a false "success"."""
    response = auth_client.post(
        "/candidate/profile/resume/upload",
        files={
            "file": (
                "resume.docx",
                b"not a real docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == "The uploaded file could not be read. Please upload a valid PDF or Word document."


def test_upload_resume_candidate_not_found(auth_client):
    with patch(
        "app.repository.candidate_repo.CandidateProfileRepo.get_profile_by_user_id",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.repository.candidate_repo.CandidateProfileRepo.get_user_by_id",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = auth_client.post(
            "/candidate/profile/resume/upload",
            files={"file": ("resume.pdf", _make_pdf_bytes(), "application/pdf")},
        )

    assert response.status_code == 404
    assert response.json()["message"] == "Candidate profile not found"


def test_download_active_resume_success(auth_client, tmp_path):
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4")

    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.get_resume_download",
        new_callable=AsyncMock,
        return_value=DumpableResult(resume_id="resume-1", file_name="resume.pdf", file_path=str(resume_path)),
    ) as service:
        response = auth_client.get("/candidate/profile/resume/download")

    assert response.status_code == 200
    body = response.json()

    assert body["message"] == "Resume download URL generated"
    assert "url" in body["data"]
    service.assert_awaited_once()


def test_download_active_resume_file_success(auth_client):
    # Byte-streaming download endpoint (fixes the "no error on failed
    # download" bug): the frontend awaits this single same-origin call
    # instead of window.open()-ing a presigned S3 URL, so it can actually
    # detect a failed/interrupted transfer.
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.get_resume_download_file",
        new_callable=AsyncMock,
        return_value=(b"%PDF-1.4 raw bytes", "resume.pdf", "application/pdf"),
    ) as service:
        response = auth_client.get("/candidate/profile/resume/download-file")

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 raw bytes"
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="resume.pdf"' in response.headers["content-disposition"]
    service.assert_awaited_once_with(ANY, ANY)


def test_download_resume_file_by_id_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.get_resume_download_file",
        new_callable=AsyncMock,
        return_value=(b"docx-bytes", "resume-v2.docx", None),
    ) as service:
        response = auth_client.get("/candidate/profile/resumes/resume-2/download-file")

    assert response.status_code == 200
    assert response.content == b"docx-bytes"
    # Falls back to octet-stream when S3 doesn't report a content type.
    assert response.headers["content-type"] == "application/octet-stream"
    assert 'filename="resume-v2.docx"' in response.headers["content-disposition"]
    service.assert_awaited_once_with(ANY, ANY, "resume-2")


def test_download_resume_file_not_found(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.get_resume_download_file",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Resume file not found"),
    ):
        response = auth_client.get("/candidate/profile/resume/download-file")

    assert response.status_code == 404
    assert response.json()["message"] == "Resume file not found"


def test_favourite_jobs_alias_success(auth_client):
    with patch(
        "app.controller.candidate_controller.candidate.CandidateProfileService.list_saved_jobs",
        new_callable=AsyncMock,
        return_value=DumpableResult(total=0, page=1, page_size=20, items=[]),
    ):
        response = auth_client.get("/candidate/favourite-jobs")

    assert response.status_code == 200
    assert response.json()["message"] == "Favourite jobs fetched successfully"
