from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


_WORK_PREFERENCE_CANONICAL: dict[str, str] = {
    "REMOTE": "Remote",
    "REMOTE_WORK": "Remote",
    "REMOTE-WORK": "Remote",
    "REMOTEWORK": "Remote",
    "REMOTE WORK": "Remote",

    "ONSITE": "Onsite",
    "ON_SITE": "Onsite",
    "ON-SITE": "Onsite",
    "ON_SITEWORK": "Onsite",

    "HYBRID": "Hybrid",
}

_EMPLOYMENT_TYPE_CANONICAL: dict[str, str] = {
    "FULL_TIME": "FULL_TIME",
    "FULLTIME": "FULL_TIME",
    "FULL-TIME": "FULL_TIME",
    "PART_TIME": "PART_TIME",
    "PARTTIME": "PART_TIME",
    "PART-TIME": "PART_TIME",
    "CONTRACT": "CONTRACT",
    "INTERNSHIP": "INTERNSHIP",
}


def _normalize_work_preference(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None

    v = str(raw).strip()
    if not v:
        return None

    upper = v.upper()
    # Normalize separators to underscore for robust keying.
    upper_sep = re.sub(r"[\s]+", "_", upper).replace("-", "_")
    key_compact = re.sub(r"[^A-Z]", "", upper)  # letters only

    for candidate in (upper, upper_sep, key_compact):
        if candidate in _WORK_PREFERENCE_CANONICAL:
            return _WORK_PREFERENCE_CANONICAL[candidate]

    raise ValueError("Invalid work_preference")


def _normalize_employment_type(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None

    v = str(raw).strip()
    if not v:
        return None

    upper = v.upper()
    upper_sep = re.sub(r"[\s]+", "_", upper).replace("-", "_")
    key_compact = re.sub(r"[^A-Z]", "", upper)

    for candidate in (upper, upper_sep, key_compact):
        if candidate in _EMPLOYMENT_TYPE_CANONICAL:
            return _EMPLOYMENT_TYPE_CANONICAL[candidate]

    return upper_sep


class CandidateJobSearchQuery(BaseModel):
    search: Optional[str] = Field(default=None, max_length=100, description="Keyword search")
    location: Optional[str] = Field(default=None, max_length=100)
    company: Optional[str] = Field(default=None, max_length=100)

    employment_type: Optional[str] = Field(default=None, max_length=50)

    # Preferred API (future-proof)
    experience: Optional[int] = Field(default=None, description="Years of experience (numeric)")

    # Backward compatible API (legacy)
    experience_level: Optional[str] = Field(
        default=None,
        description="Legacy labels: Fresher, 1-3 Years, 3-5 Years, 5+ Years",
    )

    work_preference: Optional[str] = None



    salary_min: Optional[float] = Field(default=None, ge=0)
    salary_max: Optional[float] = Field(default=None, ge=0)

    skills: Optional[List[str]] = None

    posted_within: Optional[str] = Field(default=None, description="24h | 7d | 30d")

    sort: Optional[str] = Field(default="Relevance", description="Newest | Relevance")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("search")
    @classmethod
    def _validate_search(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 100:
            raise ValueError("search max_length is 100")
        return v

    @field_validator("location", "company")
    @classmethod
    def _validate_optional_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("work_preference", mode="before")
    @classmethod
    def _normalize_work_pref_validator(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_work_preference(v)

    @field_validator("employment_type", mode="before")
    @classmethod
    def _normalize_employment_type_validator(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_employment_type(v)

    @field_validator("experience", mode="before")
    @classmethod
    def _validate_experience(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, bool):
            raise ValueError("experience must be an integer")
        try:
            iv = int(v)
        except Exception:
            raise ValueError("Invalid experience")
        if iv < 0:
            raise ValueError("experience must be >= 0")
        return iv

    @field_validator("experience_level", mode="before")
    @classmethod
    def _normalize_experience_level(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        normalized = re.sub(r"\s+", " ", s.lower()).strip()
        mapping = {
            "fresher": "Fresher",
            "1-3 years": "1-3 Years",
            "1 - 3 years": "1-3 Years",
            "1-3": "1-3 Years",
            "3-5 years": "3-5 Years",
            "3 - 5 years": "3-5 Years",
            "3-5": "3-5 Years",
            "5+ years": "5+ Years",
            "5+": "5+ Years",
        }
        normalized = normalized.replace("–", "-")
        return mapping.get(normalized, s)

    @field_validator("skills")
    @classmethod
    def _normalize_skills(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        out: list[str] = []
        for s in v:
            if s is None:
                continue
            s2 = str(s).strip()
            if s2:
                out.append(s2)
        return out or None

    @field_validator("salary_max")
    @classmethod
    def _validate_salary_range(cls, v: Optional[float], info):
        if v is None:
            return None
        salary_min = info.data.get("salary_min")
        if salary_min is not None and v < salary_min:
            raise ValueError("salary_max must be >= salary_min")
        return v

    @field_validator("posted_within")
    @classmethod
    def _validate_posted_within(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        normalized = s.lower()
        mapping = {
            "24h": "24h",
            "24hr": "24h",
            "24hrs": "24h",
            "7d": "7d",
            "7day": "7d",
            "7days": "7d",
            "30d": "30d",
            "30day": "30d",
            "30days": "30d",
        }
        if normalized not in mapping:
            raise ValueError("Invalid posted_within")
        return mapping[normalized]

    @field_validator("sort")
    @classmethod
    def _validate_sort(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return "Relevance"
        s = str(v).strip()
        if not s:
            return "Relevance"
        normalized = s.lower()
        mapping = {"newest": "Newest", "relevance": "Relevance"}
        if normalized not in mapping:
            raise ValueError("Invalid sort")
        return mapping[normalized]


class CandidateJobCardResponse(BaseModel):
    job_id: str
    job_title: str
    job_slug: str
    description_preview: Optional[str] = Field(
        default=None,
        description="Plain-text job description preview, capped at 120 characters.",
        examples=[
            "We are looking for a Senior Python Developer with strong experience in FastAPI, PostgreSQL, Docker and..."
        ],
    )

    company_name: Optional[str] = None
    company_logo: Optional[str] = None

    location: Optional[str] = None
    salary_range: Optional[str] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    employment_type: Optional[str] = None
    work_preference: Optional[str] = None

    experience_required: Optional[str] = None
    job_description: Optional[str] = None
    posted_date: Optional[datetime] = None

    skills: List[str] = []
    is_saved: bool = False
    already_applied: bool = False
    application_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CandidateCompanyInfoResponse(BaseModel):
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    logo_path: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None
    founded_year: Optional[int] = None
    location: Optional[str] = None
    headquarters_country: Optional[str] = None
    headquarters_state: Optional[str] = None
    headquarters_city: Optional[str] = None
    verification_status: Optional[str] = None


class CandidateRecruiterPublicInfoResponse(BaseModel):
    recruiter_id: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    profile_photo: Optional[str] = None
    candidate_response_time: Optional[str] = None
    interview_mode: Optional[str] = None
    languages: List[str] = Field(default_factory=list)


class CandidateJobDetailsResponse(BaseModel):
    job_id: str
    job_title: str
    job_slug: str

    company_name: Optional[str] = None
    company_logo: Optional[str] = None

    location: Optional[str] = None
    country_id: Optional[str] = None
    location_id: Optional[str] = None
    custom_city: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_range: Optional[str] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None

    employment_type: Optional[str] = None
    work_preference: Optional[str] = None
    workplace_type: Optional[str] = None
    experience_required: Optional[str] = None
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    job_category: Optional[str] = None
    seniority_level: Optional[str] = None
    team: Optional[str] = None
    team_size: Optional[str] = None
    education: Optional[str] = None

    job_description: Optional[str] = None
    responsibilities: List[str] = []
    requirements: List[str] = []
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    benefits: List[str] = []
    application_instructions: Optional[str] = None
    working_hours: Optional[str] = None
    office_location: Optional[str] = None
    map_url: Optional[str] = None
    skills: List[str] = []

    posted_date: Optional[datetime] = None
    updated_date: Optional[datetime] = None
    application_deadline: Optional[datetime] = None
    number_of_openings: Optional[int] = None
    job_status: Optional[str] = None
    company_info: Optional[CandidateCompanyInfoResponse] = None
    recruiter_public_info: Optional[CandidateRecruiterPublicInfoResponse] = None

    is_saved: bool = False
    already_applied: bool = False
    application_status: Optional[str] = None

    recommended_jobs: List[CandidateJobCardResponse] = []

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "job_id": "job-id",
                "job_title": "Senior Python Developer",
                "job_slug": "senior-python-developer",
                "company_name": "ABC Technologies",
                "location": "Hyderabad",
                "job_description": "<p>Complete candidate-visible job description.</p>",
                "responsibilities": ["Build APIs", "Review backend designs"],
                "requirements": ["5+ years backend experience"],
                "required_skills": ["Python", "FastAPI", "PostgreSQL"],
                "preferred_skills": [],
                "experience_min": 5,
                "experience_max": 8,
                "employment_type": "FULL_TIME",
                "work_preference": "HYBRID",
                "workplace_type": "HYBRID",
                "salary_min": 2500000,
                "salary_max": 3500000,
                "salary_currency": "INR",
                "salary_period": "Yearly",
                "number_of_openings": 2,
                "job_status": "PUBLISHED",
                "already_applied": True,
                "is_saved": True,
                "application_status": "APPLIED",
            }
        },
    )


class CandidateJobSearchResponse(BaseModel):
    total_records: int
    page: int
    page_size: int
    results: List[CandidateJobCardResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_records": 1,
                "page": 1,
                "page_size": 20,
                "results": [
                    {
                        "job_id": "job-id",
                        "job_title": "Senior Python Developer",
                        "job_slug": "senior-python-developer",
                        "company_name": "ABC Technologies",
                        "location": "Hyderabad",
                        "description_preview": "We are looking for a Senior Python Developer with strong experience in FastAPI, PostgreSQL, Docker and...",
                        "employment_type": "FULL_TIME",
                        "experience_required": "5-8 Years",
                        "posted_date": "2026-07-29T10:00:00Z",
                    }
                ],
            }
        }
    )


class CandidateJobSuggestionsResponse(BaseModel):
    query: str
    did_you_mean: Optional[str] = None
    suggestions: List[str] = []
    jobs: List[CandidateJobCardResponse] = Field(default_factory=list)

