from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app
from app.service.document_text_extraction_service import (
    MAX_DOCUMENT_FILENAME_LENGTH,
    MAX_DOCUMENT_SIZE_BYTES,
    DocumentTextExtractionService,
)
from app.schema.job import MAX_JOB_DESCRIPTION_LENGTH


class FakeSession:
    async def execute(self, *args, **kwargs):
        return MagicMock(scalar_one_or_none=lambda: SimpleNamespace(id="employer-1"))

    def add(self, obj):
        pass


@pytest.fixture()
def auth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "email": "hr@example.com",
        }

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload
    return TestClient(app)


def _job(**overrides):
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
        "skills": [],
        "salary_min": 800000.0,
        "salary_max": 1200000.0,
        "no_of_openings": 2,
        "application_deadline": None,
        "company_name": "NMK Technologies",
        "contact_email": "hr@nmktechnologies.com",
        "status": "PUBLISHED",
        "closed_at": None,
        "closed_reason": None,
        "created_at": None,
        "updated_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _multipart_job_data(**overrides):
    data = {
        "job_title": "Python Backend Developer",
        "employment_type": "FULL_TIME",
        "experience_required": "2-5",
        "location": "Hyderabad",
        "work_mode": "REMOTE",
        "skills": '["Python", "FastAPI"]',
        "salary_range": "800000-1200000",
        "number_of_openings": "2",
        "application_deadline": "2099-12-31T23:59:59+00:00",
        "company_name": "NMK Technologies",
        "contact_email": "hr@nmktechnologies.com",
        "status": "PUBLISHED",
    }
    data.update(overrides)
    return data


def test_clean_text_preserves_paragraphs_and_bullets():
    raw = "  Intro   text \n\n\n \t- First   bullet\n  * Second\tbullet  "

    assert DocumentTextExtractionService.clean_text(raw) == (
        "Intro text\n\n- First bullet\n* Second bullet"
    )


def test_document_upload_rejects_unsupported_extension():
    with pytest.raises(HTTPException) as exc_info:
        DocumentTextExtractionService.extract_text_from_upload(
            filename="job.txt",
            content_type="text/plain",
            contents=b"hello",
        )

    assert exc_info.value.status_code == 400
    assert "Only PDF, DOCX, and DOC" in exc_info.value.detail


def test_document_upload_rejects_oversized_file():
    with pytest.raises(HTTPException) as exc_info:
        DocumentTextExtractionService.extract_text_from_upload(
            filename="job.pdf",
            content_type="application/pdf",
            contents=b"%PDF" + (b"x" * MAX_DOCUMENT_SIZE_BYTES),
        )

    assert exc_info.value.status_code == 400
    assert "5 MB" in exc_info.value.detail


def test_document_upload_rejects_long_filename():
    filename = ("a" * (MAX_DOCUMENT_FILENAME_LENGTH + 1)) + ".pdf"

    with pytest.raises(HTTPException) as exc_info:
        DocumentTextExtractionService.extract_text_from_upload(
            filename=filename,
            content_type="application/pdf",
            contents=b"%PDF-1.4",
        )

    assert exc_info.value.status_code == 400
    assert "file name" in exc_info.value.detail


def test_document_upload_rejects_content_type_mismatch():
    with pytest.raises(HTTPException) as exc_info:
        DocumentTextExtractionService.extract_text_from_upload(
            filename="job.pdf",
            content_type="text/plain",
            contents=b"%PDF-1.4",
        )

    assert exc_info.value.status_code == 400
    assert "content type" in exc_info.value.detail


def test_document_upload_rejects_fake_pdf_header():
    with pytest.raises(HTTPException) as exc_info:
        DocumentTextExtractionService.extract_text_from_upload(
            filename="job.pdf",
            content_type="application/pdf",
            contents=b"not actually a pdf",
        )

    assert exc_info.value.status_code == 400
    assert "could not be read" in exc_info.value.detail


def test_document_upload_rejects_extracted_text_over_description_limit(monkeypatch):
    class FakePage:
        def get_text(self, mode):
            assert mode == "text"
            return "x" * (MAX_JOB_DESCRIPTION_LENGTH + 1)

    class FakeDocument:
        def __enter__(self):
            return [FakePage()]

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeFitz:
        @staticmethod
        def open(stream, filetype):
            return FakeDocument()

    monkeypatch.setitem(sys.modules, "fitz", FakeFitz)

    with pytest.raises(HTTPException) as exc_info:
        DocumentTextExtractionService.extract_text_from_upload(
            filename="job.pdf",
            content_type="application/pdf",
            contents=b"%PDF-1.4",
        )

    assert exc_info.value.status_code == 400
    assert str(MAX_JOB_DESCRIPTION_LENGTH) in exc_info.value.detail


def test_pdf_text_extraction_uses_pymupdf(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def get_text(self, mode):
            assert mode == "text"
            return self.text

    class FakeDocument:
        def __enter__(self):
            return [FakePage("First   paragraph"), FakePage("- Bullet   point")]

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeFitz:
        @staticmethod
        def open(stream, filetype):
            assert stream == b"%PDF-1.4"
            assert filetype == "pdf"
            return FakeDocument()

    monkeypatch.setitem(sys.modules, "fitz", FakeFitz)

    assert DocumentTextExtractionService.extract_text_from_upload(
        filename="job.pdf",
        content_type="application/pdf",
        contents=b"%PDF-1.4",
    ) == "First paragraph\n\n- Bullet point"


def test_post_job_multipart_populates_empty_description_from_document(auth_client):
    with patch(
        "app.controller.employer_controller.job._get_or_create_employer_profile",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(id="employer-1"),
    ), patch(
        "app.controller.employer_controller.job.DocumentTextExtractionService.extract_text_from_upload",
        return_value="Extracted job description",
    ), patch(
        "app.controller.employer_controller.job.JobService.create_post_job",
        new_callable=AsyncMock,
        return_value=_job(description="Extracted job description"),
    ) as create_post_job:
        response = auth_client.post(
            "/jobs/",
            data=_multipart_job_data(job_description=" "),
            files={
                "job_description_document": (
                    "job-description.docx",
                    b"docx bytes",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert response.status_code == 201
    request_arg = create_post_job.await_args.kwargs["request"]
    assert request_arg.job_description == "Extracted job description"


def test_post_job_returns_clear_description_too_long_error(auth_client):
    response = auth_client.post(
        "/jobs/",
        json={
            "job_title": "Python Backend Developer",
            "job_description": "x" * (MAX_JOB_DESCRIPTION_LENGTH + 1),
            "employment_type": "FULL_TIME",
            "experience_required": "2-5",
            "location": "Hyderabad",
            "work_mode": "REMOTE",
            "skills": ["Python", "FastAPI"],
            "number_of_openings": 2,
            "application_deadline": "2099-12-31T23:59:59+00:00",
            "company_name": "NMK Technologies",
            "contact_email": "hr@nmktechnologies.com",
            "status": "PUBLISHED",
        },
    )

    assert response.status_code == 400
    assert response.json()["message"] == (
        "Job description must not exceed 5000 characters. "
        "Please upload a smaller file or shorten the description."
    )


def test_put_job_multipart_keeps_manual_description_when_document_is_present(auth_client):
    with patch(
        "app.controller.employer_controller.job.JobService.update_job",
        new_callable=AsyncMock,
        return_value=_job(description="Manual description"),
    ) as update_job, patch(
        "app.controller.employer_controller.job.DocumentTextExtractionService.extract_text_from_upload",
        return_value="Extracted job description",
    ) as extract_text:
        response = auth_client.put(
            "/jobs/job-1",
            data={"job_description": "Manual description"},
            files={
                "job_description_document": (
                    "job-description.pdf",
                    b"%PDF-1.4",
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 200
    request_arg = update_job.await_args.kwargs["request"]
    assert request_arg.job_description == "Manual description"
    extract_text.assert_not_called()
