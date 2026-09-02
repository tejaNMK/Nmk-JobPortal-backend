from datetime import datetime

import pytest
from app.utils.utc import utc_now_naive
from fastapi import HTTPException
from pydantic import ValidationError

from app.schema.profile import CompanyIndustry, CompanyProfileCreate, EmployerProfileCreate
from app.service.profile_service import MAX_UPLOAD_BYTES, _read_valid_image


VALID_COMPANY = {
    "company_name": "Acme Staffing, Inc.",
    "website": "https://example.com",
    "industry": "STAFFING",
    "company_size": "51-200",
    "founded_year": 2010,
    "headquarters_country": "United States",
    "headquarters_city": "New York",
    "description": "A staffing company focused on technical hiring.",
    "contact_email": "hr@example.com",
    "contact_phone": "+14155552671",
}

VALID_EMPLOYER = {
    "job_title": "Talent Partner",
    "experience_years": 7,
    "interview_mode": "ONLINE",
    "visibility": "PUBLIC",
}


class DummyUpload:
    def __init__(self, *, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self):
        return self._content


def test_company_profile_create_requires_required_fields():
    with pytest.raises(ValidationError):
        CompanyProfileCreate()


@pytest.mark.parametrize(
    "field,value",
    [
        ("company_name", "A"),
        ("company_name", "Bad_Name!"),
        ("description", "too short"),
        ("headquarters_country", "U"),
        ("headquarters_city", "X"),
    ],
)
def test_company_profile_create_length_and_pattern_validation(field, value):
    payload = {**VALID_COMPANY, field: value}
    with pytest.raises(ValidationError):
        CompanyProfileCreate(**payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("contact_email", "not-an-email"),
        ("website", "ftp://example.com"),
        ("contact_phone", "4155552671"),
        ("industry", "INVALID"),
        ("company_size", "1000-2000"),
        ("founded_year", utc_now_naive().year + 1),
    ],
)
def test_company_profile_create_value_validation(field, value):
    payload = {**VALID_COMPANY, field: value}
    with pytest.raises(ValidationError):
        CompanyProfileCreate(**payload)


def test_company_profile_create_sanitizes_whitespace():
    payload = {
        **VALID_COMPANY,
        "company_name": "  Acme   Staffing  ",
        "headquarters_city": "  New   York ",
    }
    result = CompanyProfileCreate(**payload)
    assert result.company_name == "Acme Staffing"
    assert result.headquarters_city == "New York"


def test_company_profile_create_normalizes_legacy_industry_value():
    payload = {**VALID_COMPANY, "industry": "TECHNOLOGY"}
    result = CompanyProfileCreate(**payload)
    assert result.industry == CompanyIndustry.IT


def test_employer_profile_create_normalizes_legacy_interview_mode_values():
    payload = {**VALID_EMPLOYER, "interview_mode": "OFFLINE"}
    result = EmployerProfileCreate(**payload)
    assert result.interview_mode == "OFFLINE"


def test_employer_profile_create_requires_required_fields():
    with pytest.raises(ValidationError):
        EmployerProfileCreate()


@pytest.mark.parametrize(
    "field,value",
    [
        ("job_title", "A"),
        ("job_title", "x" * 151),
        ("department", "x" * 151),
        ("location", "x" * 256),
        ("timezone", "x" * 101),
        ("bio", "too short"),
        ("bio", "x" * 1001),
        ("specialization_1", "x" * 151),
        ("candidate_response_time", "x" * 101),
        ("availability", "x" * 501),
    ],
)
def test_employer_profile_length_validation(field, value):
    payload = {**VALID_EMPLOYER, field: value}
    with pytest.raises(ValidationError):
        EmployerProfileCreate(**payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("experience_years", -1),
        ("experience_years", 61),
        ("interview_mode", "CHAT"),
        ("visibility", "EVERYONE"),
        ("linkedin_url", "mailto:hr@example.com"),
        ("website_url", "ftp://example.com"),
        ("languages", ["x" * 151]),
    ],
)
def test_employer_profile_value_validation(field, value):
    payload = {**VALID_EMPLOYER, field: value}
    with pytest.raises(ValidationError):
        EmployerProfileCreate(**payload)


@pytest.mark.asyncio
async def test_company_logo_rejects_invalid_file_type():
    upload = DummyUpload(
        filename="logo.gif",
        content_type="image/gif",
        content=b"gif",
    )
    with pytest.raises(HTTPException) as exc:
        await _read_valid_image(upload, allowed_svg=True)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_employer_photo_rejects_svg():
    upload = DummyUpload(
        filename="photo.svg",
        content_type="image/svg+xml",
        content=b"<svg></svg>",
    )
    with pytest.raises(HTTPException) as exc:
        await _read_valid_image(upload, allowed_svg=False)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_files_larger_than_5_mb():
    upload = DummyUpload(
        filename="logo.png",
        content_type="image/png",
        content=b"x" * (MAX_UPLOAD_BYTES + 1),
    )
    with pytest.raises(HTTPException) as exc:
        await _read_valid_image(upload, allowed_svg=True)
    assert exc.value.status_code == 400
