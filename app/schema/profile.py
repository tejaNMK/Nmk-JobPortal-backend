from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID
from app.utils.utc import utc_now

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator


COMPANY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 &,.'()-]+$")
MULTISPACE_PATTERN = re.compile(r"\s+")


class CompanyIndustry(str, Enum):
    # New canonical enum value
    IT = "IT"
    HEALTHCARE = "HEALTHCARE"
    FINANCE = "FINANCE"
    EDUCATION = "EDUCATION"
    RETAIL = "RETAIL"
    MANUFACTURING = "MANUFACTURING"
    STAFFING = "STAFFING"
    CONSULTING = "CONSULTING"
    OTHER = "OTHER"


class CompanySize(str, Enum):
    SIZE_1_10 = "1-10"
    SIZE_11_50 = "11-50"
    SIZE_51_200 = "51-200"
    SIZE_201_500 = "201-500"
    SIZE_500_PLUS = "500+"


class VerificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class EmployerProfileVisibility(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    COMPANY_ONLY = "COMPANY_ONLY"


class EmployerInterviewMode(str, Enum):
    PHONE = "PHONE"
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    HYBRID = "HYBRID"




def _current_year() -> int:
    return utc_now().year


def _normalize_url(value: Optional[HttpUrl]) -> Optional[str]:
    return str(value) if value is not None else None


def _normalize_datetime_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)
        text = re.sub(r"([+-]\d{2})$", r"\1:00", text)
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return value
    return value


def _validate_e164(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not re.fullmatch(r"^\+[1-9]\d{7,14}$", value):
        raise ValueError("Phone number must be in E164 format")
    return value


def _trim(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _trim_optional(value: Any) -> Any:
    value = _trim(value)
    if value == "":
        return None
    return value


def _normalize_spaces(value: Any) -> Any:
    value = _trim(value)
    if isinstance(value, str):
        return MULTISPACE_PATTERN.sub(" ", value)
    return value


def _normalize_optional_spaces(value: Any) -> Any:
    value = _normalize_spaces(value)
    if value == "":
        return None
    return value


class CompanyProfileBase(BaseModel):
    company_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    website: Optional[HttpUrl] = Field(default=None, max_length=255)
    industry: Optional[CompanyIndustry] = None
    company_size: Optional[CompanySize] = None
    founded_year: Optional[int] = Field(default=None, ge=1900)
    description: Optional[str] = Field(default=None, min_length=30, max_length=2000)
    headquarters_country: Optional[str] = Field(default=None, min_length=2, max_length=100)
    headquarters_state: Optional[str] = Field(default=None, max_length=100)
    headquarters_city: Optional[str] = Field(default=None, min_length=2, max_length=100)
    logo_url: Optional[str] = None
    contact_email: Optional[EmailStr] = Field(default=None, max_length=255)
    contact_phone: Optional[str] = None
    verification_status: Optional[VerificationStatus] = None
    is_public: Optional[bool] = None

    @field_validator(
        "company_name",
        "description",
        "headquarters_country",
        "headquarters_state",
        "headquarters_city",
        mode="before",
    )
    @classmethod
    def sanitize_text(cls, value: Any) -> Any:
        return _normalize_optional_spaces(value)

    @field_validator("website", "contact_email", "contact_phone", mode="before")
    @classmethod
    def sanitize_scalar(cls, value: Any) -> Any:
        return _trim_optional(value)

    @field_validator("industry", mode="before")
    @classmethod
    def normalize_industry(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().upper().replace(" ", "_")
            if normalized in {"TECHNOLOGY", "INFORMATION_TECHNOLOGY"}:
                return "IT"
        return value

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not COMPANY_NAME_PATTERN.fullmatch(value):
            raise ValueError("Company name contains unsupported characters")
        return value

    @field_validator("founded_year")
    @classmethod
    def validate_founded_year(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value > _current_year():
            raise ValueError("Founded year cannot be in the future")
        return value

    @field_validator("contact_phone")
    @classmethod
    def validate_contact_phone(cls, value: Optional[str]) -> Optional[str]:
        return _validate_e164(value)


class CompanyProfileCreate(CompanyProfileBase):
    company_name: str = Field(min_length=2, max_length=150)
    website: HttpUrl = Field(max_length=255)
    industry: CompanyIndustry
    company_size: CompanySize
    founded_year: int = Field(ge=1900)
    description: str = Field(min_length=30, max_length=2000)
    headquarters_country: str = Field(min_length=2, max_length=100)
    headquarters_city: str = Field(min_length=2, max_length=100)
    contact_email: EmailStr = Field(max_length=255)
    contact_phone: str


class CompanyProfileUpdate(CompanyProfileBase):
    pass


class CompanyProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def normalize_datetime_fields(cls, value: Any) -> Any:
        return _normalize_datetime_value(value)

    id: UUID
    company_id: str
    company_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    headquarters_country: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_city: Optional[str] = None
    logo_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    verification_status: str
    verified_at: Optional[datetime] = None
    is_public: bool
    created_at: datetime
    updated_at: datetime


class CompanySearchResponse(BaseModel):
    items: List[CompanyProfileResponse]
    total: int
    page: int
    page_size: int


class EmployerProfileBase(BaseModel):
    job_title: Optional[str] = Field(default=None, min_length=2, max_length=150)
    department: Optional[str] = Field(default=None, max_length=150)
    bio: Optional[str] = Field(default=None, min_length=20, max_length=1000)
    location: Optional[str] = Field(default=None, max_length=255)
    timezone: Optional[str] = Field(default=None, max_length=100)
    experience_years: Optional[int] = Field(default=None, ge=0, le=60)
    candidate_response_time: Optional[str] = Field(default=None, max_length=100)
    interview_mode: Optional[EmployerInterviewMode] = None
    availability: Optional[str] = Field(default=None, max_length=500)
    languages: Optional[List[str]] = None
    linkedin_url: Optional[HttpUrl] = Field(default=None, max_length=255)
    website_url: Optional[HttpUrl] = Field(default=None, max_length=255)
    profile_photo: Optional[str] = None
    visibility: Optional[EmployerProfileVisibility] = None
    specialization_1: Optional[str] = Field(default=None, max_length=150)
    specialization_2: Optional[str] = Field(default=None, max_length=150)
    specialization_3: Optional[str] = Field(default=None, max_length=150)
    specialization_4: Optional[str] = Field(default=None, max_length=150)

    @field_validator(
        "job_title",
        "department",
        "bio",
        "location",
        "timezone",
        "candidate_response_time",
        "availability",
        "specialization_1",
        "specialization_2",
        "specialization_3",
        "specialization_4",
        mode="before",
    )
    @classmethod
    def sanitize_text(cls, value: Any) -> Any:
        return _normalize_optional_spaces(value)

    @field_validator("linkedin_url", "website_url", mode="before")
    @classmethod
    def sanitize_url(cls, value: Any) -> Any:
        return _trim_optional(value)

    @field_validator("interview_mode", mode="before")
    @classmethod
    def normalize_interview_mode(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().upper().replace(" ", "_")
            if normalized in {"REMOTE", "ONLINE"}:
                return "ONLINE"
            if normalized in {"OFFLINE", "ONSITE", "IN_PERSON", "INPERSON"}:
                return "OFFLINE"
            if normalized in {"HYBRID"}:
                return "HYBRID"
            if normalized in {"PHONE"}:
                return "PHONE"
        return value

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        cleaned = [_normalize_spaces(item) for item in value if item and str(item).strip()]
        if len(cleaned) != len(value):
            raise ValueError("Languages must be non-empty strings")
        if any(len(item) > 150 for item in cleaned):
            raise ValueError("Each language must be 150 characters or fewer")
        return cleaned


class EmployerProfileCreate(EmployerProfileBase):
    job_title: str = Field(min_length=2, max_length=150)
    experience_years: int = Field(ge=0, le=60)
    interview_mode: EmployerInterviewMode
    visibility: EmployerProfileVisibility


class EmployerProfileUpdate(EmployerProfileBase):
    pass


class EmployerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def normalize_datetime_fields(cls, value: Any) -> Any:
        return _normalize_datetime_value(value)

    id: str
    user_id: UUID
    job_title: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    experience_years: Optional[int] = None
    candidate_response_time: Optional[str] = None
    interview_mode: Optional[str] = None
    availability: Optional[str] = None
    languages: Optional[List[str]] = None
    linkedin_url: Optional[str] = None
    website_url: Optional[str] = None
    profile_photo: Optional[str] = None
    visibility: str
    specialization_1: Optional[str] = None
    specialization_2: Optional[str] = None
    specialization_3: Optional[str] = None
    specialization_4: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProfileCompletionResponse(BaseModel):
    completion_percentage: int
    missing_fields: List[str]


class EmployerDashboardSummary(BaseModel):
    profile_completion: int
    candidates_contacted: int
    response_rate: int
    interviews_scheduled: int
    candidate_rating: float
    active_jobs: List[dict[str, Any]]
    recent_activity: List[dict[str, Any]]


def dump_profile_update(model: BaseModel) -> dict[str, Any]:
    data = model.model_dump(exclude_unset=True)
    for key in ("website", "linkedin_url", "website_url"):
        if key in data:
            data[key] = _normalize_url(data[key])
    for key in ("industry", "company_size", "verification_status", "visibility", "interview_mode"):
        if key in data and data[key] is not None:
            data[key] = data[key].value
    if "contact_email" in data and data["contact_email"] is not None:
        data["contact_email"] = str(data["contact_email"])
    return data
