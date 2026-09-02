from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.utils.slug import slugify_job_title
from app.utils.job_time import posted_display_date


def _normalize_choice(value: str, choices: dict[str, str]) -> str:
    if value is None:
        return value
    key = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    return choices.get(key, key)

EMPLOYMENT_TYPE_CHOICES = {
    "FULL_TIME": "FULL_TIME",
    "FULLTIME": "FULL_TIME",
    "PART_TIME": "PART_TIME",
    "PARTTIME": "PART_TIME",
    "CONTRACT": "CONTRACT",
    "INTERNSHIP": "INTERNSHIP",
}

WORK_MODE_CHOICES = {
    "ONSITE": "ONSITE",
    "ON_SITE": "ONSITE",
    "REMOTE": "REMOTE",
    "HYBRID": "HYBRID",
}

JOB_STATUS_CHOICES = {
    "DRAFT": "DRAFT",
    "CLOSED": "CLOSED",
    "EXPIRED": "EXPIRED",
    "PUBLISHED": "PUBLISHED",
}

MAX_JOB_DESCRIPTION_LENGTH = 5000
MAX_SKILL_LENGTH = 50
MAX_JOB_DETAIL_LIST_ITEMS = 20
MAX_RESPONSIBILITY_LENGTH = 300
MAX_REQUIREMENT_LENGTH = 300
MAX_BENEFIT_LENGTH = 80

SkillItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SKILL_LENGTH),
]
ResponsibilityItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_RESPONSIBILITY_LENGTH),
]
RequirementItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_REQUIREMENT_LENGTH),
]
BenefitItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_BENEFIT_LENGTH),
]


def _normalize_text_list(
    value: Optional[List[str]],
    *,
    field_label: str,
    max_items: int,
    max_item_length: int,
) -> Optional[List[str]]:
    if value is None:
        return None
    if len(value) > max_items:
        raise ValueError(f"{field_label} can contain at most {max_items} items")

    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text:
            raise ValueError(f"{field_label} items cannot be blank")
        if len(text) > max_item_length:
            raise ValueError(f"{field_label} items must be at most {max_item_length} characters")
        normalized.append(text)

    return normalized or None


def _validate_single_or_range(raw: Optional[str], field_label: str) -> None:
    if raw is None:
        return
    value = raw.strip()
    if not value:
        raise ValueError(f"{field_label} cannot be blank")
    if "-" in value:
        parts = [part.strip() for part in value.split("-", 1)]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid {field_label} format")
        if not parts[0].isdigit() or not parts[1].isdigit():
            raise ValueError(f"Invalid {field_label} numeric format")
        if int(parts[0]) > int(parts[1]):
            raise ValueError(f"Invalid {field_label} range")
        return
    if not value.isdigit():
        raise ValueError(f"Invalid {field_label} numeric format")


class PostJobRequestSchema(BaseModel):
    job_title: str = Field(
        ...,
        min_length=3,
        max_length=100,
        examples=["Python Backend Developer"],
    )
    job_description: str = Field(
        ...,
        max_length=MAX_JOB_DESCRIPTION_LENGTH,
        examples=["Build and maintain FastAPI services."],
    )
    employment_type: str = Field(..., examples=["FULL_TIME"])
    experience_required: str = Field(
        ...,
        max_length=20,
        examples=["2-5"],
    )
    location: Optional[str] = Field(default=None, max_length=100, examples=["Hyderabad"])
    country_id: Optional[str] = Field(default=None, max_length=100, examples=["country-id-for-thailand"])
    location_id: Optional[str] = Field(default=None, max_length=100, examples=["location-id-for-bangkok"])
    custom_city: Optional[str] = Field(default=None, max_length=100, examples=["Chiang Rai"])
    work_mode: str = Field(..., examples=["REMOTE"])
    skills: List[SkillItem] = Field(
        ..., min_length=1, max_length=20, examples=[["Python", "FastAPI", "PostgreSQL"]]
    )
    salary_range: Optional[str] = Field(
        default=None,
        max_length=50,
        examples=["800000-1200000"],
    )
    salary_currency: Optional[str] = Field(default="USD", max_length=10, examples=["USD"])
    salary_period: Optional[str] = Field(default="Monthly", max_length=20, examples=["Monthly"])
    number_of_openings: int = Field(..., ge=1, le=9999, examples=[2])
    application_deadline: Optional[datetime] = Field(
        default=None, examples=["2099-12-31T23:59:59+00:00"]
    )
    company_name: str = Field(..., max_length=100, examples=["NMK Technologies"])
    contact_email: str = Field(..., max_length=50, examples=["hr@nmktechnologies.com"])
    job_category: Optional[str] = Field(default=None, max_length=100, examples=["Product & Engineering"])
    seniority_level: Optional[str] = Field(default=None, max_length=100, examples=["Lead / Manager"])
    team: Optional[str] = Field(default=None, max_length=100, examples=["Product Delivery"])
    team_size: Optional[str] = Field(default=None, max_length=100, examples=["25+ collaborators"])
    education: Optional[str] = Field(default=None, max_length=150, examples=["Master's preferred"])
    responsibilities: Optional[List[ResponsibilityItem]] = Field(
        default=None,
        max_length=MAX_JOB_DETAIL_LIST_ITEMS,
        examples=[["Own delivery roadmap", "Mentor scrum leads"]],
    )
    requirements: Optional[List[RequirementItem]] = Field(
        default=None,
        max_length=MAX_JOB_DETAIL_LIST_ITEMS,
        examples=[["5+ years leading implementations", "Strong stakeholder management"]],
    )
    benefits: Optional[List[BenefitItem]] = Field(
        default=None,
        max_length=MAX_JOB_DETAIL_LIST_ITEMS,
        examples=[["Annual bonus", "Hybrid work flexibility"]],
    )
    application_instructions: Optional[str] = Field(
        default=None,
        max_length=2000,
        examples=["Attach your resume and share 2-3 project highlights."],
    )
    working_hours: Optional[str] = Field(default=None, max_length=100, examples=["Monday - Friday, 9am-5pm"])
    office_location: Optional[str] = Field(default=None, max_length=255, examples=["Dubai, United Arab Emirates"])
    map_url: Optional[str] = Field(default=None, max_length=1000, examples=["https://maps.google.com/..."])

    status: str = Field(default="PUBLISHED", examples=["PUBLISHED"])

    @field_validator("employment_type", mode="before")
    @classmethod
    def normalize_employment_type(cls, value: str) -> str:
        return _normalize_choice(value, EMPLOYMENT_TYPE_CHOICES)

    @field_validator("work_mode", mode="before")
    @classmethod
    def normalize_work_mode(cls, value: str) -> str:
        return _normalize_choice(value, WORK_MODE_CHOICES)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return _normalize_choice(value, JOB_STATUS_CHOICES)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: List[str]) -> List[str]:
        normalized = _normalize_text_list(
            value,
            field_label="Skills",
            max_items=20,
            max_item_length=MAX_SKILL_LENGTH,
        )
        if not normalized:
            raise ValueError("At least 1 skill is required")
        return normalized

    @field_validator("responsibilities")
    @classmethod
    def validate_responsibilities(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_text_list(
            value,
            field_label="Responsibilities",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_RESPONSIBILITY_LENGTH,
        )

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_text_list(
            value,
            field_label="Requirements",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_REQUIREMENT_LENGTH,
        )

    @field_validator("benefits")
    @classmethod
    def validate_benefits(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_text_list(
            value,
            field_label="Benefits",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_BENEFIT_LENGTH,
        )

    @model_validator(mode="after")
    def validate_rules(self):
        allowed_employment = set(EMPLOYMENT_TYPE_CHOICES.values())
        allowed_work_mode = set(WORK_MODE_CHOICES.values())
        allowed_status = set(JOB_STATUS_CHOICES.values())

        def _reject_blank(value: Optional[str], field_name: str) -> Optional[str]:
            if value is None:
                return None
            v = value.strip()
            if not v:
                raise ValueError(f"{field_name} cannot be blank")
            return v

        self.job_title = _reject_blank(self.job_title, "Job Title")
        self.job_description = _reject_blank(self.job_description, "Job Description")
        self.location = _reject_blank(self.location, "Location")
        self.country_id = _reject_blank(self.country_id, "Country")
        self.location_id = _reject_blank(self.location_id, "City")
        self.custom_city = _reject_blank(self.custom_city, "Custom City")
        self.company_name = _reject_blank(self.company_name, "Company Name")

        if self.employment_type not in allowed_employment:
            raise ValueError("Invalid employment type")
        if self.work_mode not in allowed_work_mode:
            raise ValueError("Invalid work mode")
        if self.status not in allowed_status:
            raise ValueError("Invalid status")

        if (self.location_id is not None or self.custom_city is not None) and self.country_id is None:
            raise ValueError("country_id is required when selecting or entering a city")
        if self.location_id is not None and self.custom_city is not None:
            raise ValueError("Use either location_id or custom_city, not both")
        if self.location is None and self.country_id is None:
            raise ValueError("Location is required")

        self.contact_email = self.contact_email.strip()
        if not self.contact_email:
            raise ValueError("Contact Email cannot be blank")

        self.experience_required = self.experience_required.strip()
        _validate_single_or_range(self.experience_required, "Experience Required")
        if self.salary_range is not None:
            self.salary_range = self.salary_range.strip()
            _validate_single_or_range(self.salary_range, "Salary Range")

        return self


class UpdateJobRequestSchema(BaseModel):
    job_title: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=100,
        examples=["Python Backend Developer"],
    )
    job_description: Optional[str] = Field(
        default=None,
        max_length=MAX_JOB_DESCRIPTION_LENGTH,
        examples=["Build and maintain FastAPI services."],
    )
    employment_type: Optional[str] = Field(default=None, examples=["FULL_TIME"])
    experience_required: Optional[str] = Field(
        default=None,
        max_length=20,
        examples=["2-5"],
    )
    location: Optional[str] = Field(default=None, max_length=100, examples=["Hyderabad"])
    country_id: Optional[str] = Field(default=None, max_length=100, examples=["country-id-for-thailand"])
    location_id: Optional[str] = Field(default=None, max_length=100, examples=["location-id-for-bangkok"])
    custom_city: Optional[str] = Field(default=None, max_length=100, examples=["Chiang Rai"])
    work_mode: Optional[str] = Field(default=None, examples=["REMOTE"])
    skills: Optional[List[SkillItem]] = Field(
        default=None,
        min_length=1,
        max_length=20,
        examples=[["Python", "FastAPI", "PostgreSQL"]],
    )
    salary_range: Optional[str] = Field(
        default=None,
        max_length=50,
        examples=["800000-1200000"],
    )
    salary_currency: Optional[str] = Field(default=None, max_length=10, examples=["USD"])
    salary_period: Optional[str] = Field(default=None, max_length=20, examples=["Monthly"])
    number_of_openings: Optional[int] = Field(default=None, ge=1, le=9999, examples=[2])
    application_deadline: Optional[datetime] = Field(default=None, examples=["2099-12-31T23:59:59+00:00"])
    company_name: Optional[str] = Field(
        default=None,
        max_length=100,
        examples=["NMK Technologies"],
    )
    contact_email: Optional[str] = Field(
        default=None,
        max_length=50,
        examples=["hr@nmktechnologies.com"],
    )
    job_category: Optional[str] = Field(default=None, max_length=100, examples=["Product & Engineering"])
    seniority_level: Optional[str] = Field(default=None, max_length=100, examples=["Lead / Manager"])
    team: Optional[str] = Field(default=None, max_length=100, examples=["Product Delivery"])
    team_size: Optional[str] = Field(default=None, max_length=100, examples=["25+ collaborators"])
    education: Optional[str] = Field(default=None, max_length=150, examples=["Master's preferred"])
    responsibilities: Optional[List[ResponsibilityItem]] = Field(default=None, max_length=MAX_JOB_DETAIL_LIST_ITEMS)
    requirements: Optional[List[RequirementItem]] = Field(default=None, max_length=MAX_JOB_DETAIL_LIST_ITEMS)
    benefits: Optional[List[BenefitItem]] = Field(default=None, max_length=MAX_JOB_DETAIL_LIST_ITEMS)
    application_instructions: Optional[str] = Field(default=None, max_length=2000)
    working_hours: Optional[str] = Field(default=None, max_length=100)
    office_location: Optional[str] = Field(default=None, max_length=255)
    map_url: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[str] = Field(default=None, examples=["PUBLISHED"])



    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_title": "Senior Python Developer",
                "location": "Hyderabad",
                "status": "PUBLISHED",
            }
        }
    )

    @field_validator("employment_type", mode="before")
    @classmethod
    def normalize_employment_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_choice(value, EMPLOYMENT_TYPE_CHOICES)

    @field_validator("work_mode", mode="before")
    @classmethod
    def normalize_work_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_choice(value, WORK_MODE_CHOICES)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_choice(value, JOB_STATUS_CHOICES)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_text_list(
            value,
            field_label="Skills",
            max_items=20,
            max_item_length=MAX_SKILL_LENGTH,
        )

    @field_validator("responsibilities")
    @classmethod
    def validate_responsibilities(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_text_list(
            value,
            field_label="Responsibilities",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_RESPONSIBILITY_LENGTH,
        )

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_text_list(
            value,
            field_label="Requirements",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_REQUIREMENT_LENGTH,
        )

    @field_validator("benefits")
    @classmethod
    def validate_benefits(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _normalize_text_list(
            value,
            field_label="Benefits",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_BENEFIT_LENGTH,
        )

    @model_validator(mode="after")
    def validate_rules(self):
        allowed_employment = set(EMPLOYMENT_TYPE_CHOICES.values())
        allowed_work_mode = set(WORK_MODE_CHOICES.values())
        allowed_status = set(JOB_STATUS_CHOICES.values())

        def _reject_blank(value: Optional[str], field_name: str) -> Optional[str]:
            if value is None:
                return None
            v = value.strip()
            if not v:
                raise ValueError(f"{field_name} cannot be blank")
            return v

        self.job_title = _reject_blank(self.job_title, "Job Title")
        self.job_description = _reject_blank(self.job_description, "Job Description")
        self.location = _reject_blank(self.location, "Location")
        self.country_id = _reject_blank(self.country_id, "Country")
        self.location_id = _reject_blank(self.location_id, "City")
        self.custom_city = _reject_blank(self.custom_city, "Custom City")
        self.company_name = _reject_blank(self.company_name, "Company Name")

        if (self.location_id is not None or self.custom_city is not None) and self.country_id is None:
            raise ValueError("country_id is required when selecting or entering a city")

        if self.location_id is not None and self.custom_city is not None:
            raise ValueError("Use either location_id or custom_city, not both")

        if self.contact_email is not None:
            self.contact_email = self.contact_email.strip()
            if not self.contact_email:
                raise ValueError("Contact Email cannot be blank")


        if self.experience_required is not None:
            v = self.experience_required.strip()
            if not v:
                raise ValueError("Experience Required cannot be blank")
            self.experience_required = v
            if self.experience_required is None:
                raise ValueError("Experience Required cannot be blank")

        if self.employment_type is not None and self.employment_type not in allowed_employment:
            raise ValueError("Invalid employment type")
        # Do NOT validate work_mode here; the update payload may omit it.
        # Also, avoid rejecting values that are valid in DB/API but not in this validator.
        # If work_mode is required later, validate in JobService.
        # (No-op)
        if self.work_mode is not None:
            self.work_mode = _normalize_choice(self.work_mode, WORK_MODE_CHOICES)



        # IMPORTANT: Update semantics should not require fields that are not being updated.
        # (The model_validator currently normalizes/validates optional fields; keep checks fully guarded.)
        if self.status is not None and self.status not in allowed_status:
            raise ValueError("Invalid status")

        if self.skills is not None:
            if len(self.skills) < 1:
                raise ValueError("At least 1 skill is required")
            if len(self.skills) > 20:
                raise ValueError("Maximum 20 skills allowed")

            normalized_skills = [str(s).strip() for s in self.skills if str(s).strip()]
            if len(normalized_skills) < 1:
                raise ValueError("At least 1 skill is required")
            if len(normalized_skills) > 20:
                raise ValueError("Maximum 20 skills allowed")
            if any(len(skill) > MAX_SKILL_LENGTH for skill in normalized_skills):
                raise ValueError(f"Skills must be at most {MAX_SKILL_LENGTH} characters each")
            self.skills = normalized_skills

        self.responsibilities = _normalize_text_list(
            self.responsibilities,
            field_label="Responsibilities",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_RESPONSIBILITY_LENGTH,
        )
        self.requirements = _normalize_text_list(
            self.requirements,
            field_label="Requirements",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_REQUIREMENT_LENGTH,
        )
        self.benefits = _normalize_text_list(
            self.benefits,
            field_label="Benefits",
            max_items=MAX_JOB_DETAIL_LIST_ITEMS,
            max_item_length=MAX_BENEFIT_LENGTH,
        )

        if self.number_of_openings is not None:
            if self.number_of_openings <= 0 or self.number_of_openings > 9999:
                raise ValueError("Number of Openings must be a positive integer <= 9999")

        def _parse_single_or_range(raw: Optional[str], field_label: str):
            if raw is None:
                return None
            v = raw.strip()
            if not v:
                raise ValueError(f"{field_label} cannot be blank")
            if "-" in v:
                parts = [p.strip() for p in v.split("-", 1)]
                if len(parts) != 2 or not parts[0] or not parts[1]:
                    raise ValueError(f"Invalid {field_label} format")
                if not parts[0].isdigit() or not parts[1].isdigit():
                    raise ValueError(f"Invalid {field_label} numeric format")
                a = int(parts[0])
                b = int(parts[1])
                if a > b:
                    raise ValueError(f"Invalid {field_label} range")
                return a, b
            if not v.isdigit():
                raise ValueError(f"Invalid {field_label} numeric format")
            return int(v), None

        if self.experience_required is not None:
            _parse_single_or_range(self.experience_required, "Experience Required")

        if self.salary_range is not None:
            _parse_single_or_range(self.salary_range, "Salary Range")

        return self





# ─────────────────────────────────────────────────────────────────────────────
# EMP-JOB-003: Job List (Employer)
# ─────────────────────────────────────────────────────────────────────────────

_JOB_TITLE_MAX_LEN = 100
_JOB_TITLE_LINK_MAX_LEN = 150


def _validate_job_title_keywords(value: str) -> str:
    v = (value or "").strip()
    if len(v) > _JOB_TITLE_MAX_LEN:
        raise ValueError("Search keywords must be at most 100 characters")
   
    if v:
        allowed = re.compile(r"^[A-Za-z0-9\s\-\.,/()&'\"]*$")
        if not allowed.match(v):
            raise ValueError("Search keywords contain invalid characters")
    return v


class JobListFiltersSchema(BaseModel):
    search: str = Field(default="", description="Job title / keywords")
    location: Optional[str] = None
    employment_type: Optional[str] = None
    status: Optional[str] = None
    experience: Optional[str] = None



    sort_by: Optional[Literal[
        "POSTED_DATE_DESC",
        "POSTED_DATE_ASC",
        "JOB_TITLE_ASC",
        "JOB_TITLE_DESC",
        "LOCATION_ASC",
        "LOCATION_DESC",
    ]] = None

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    clear_filters: bool = Field(default=False)


    @model_validator(mode="after")
    def validate_rules(self):
        self.search = _validate_job_title_keywords(self.search)
        if self.status is not None:
            normalized = str(self.status).strip().upper().replace("-", "_").replace(" ", "_")
            allowed = set(JOB_STATUS_CHOICES) | set(JOB_STATUS_CHOICES.values()) | {"ALL"}
            if normalized not in allowed:
                raise ValueError("Invalid status")
            self.status = normalized if normalized == "ALL" else JOB_STATUS_CHOICES.get(normalized, normalized)
        return self



class JobListGridRowSchema(BaseModel):
    job_id: str
    job_title: str
    job_slug: str

    location: Optional[str]
    employment_type: Optional[str]
    status: str
    posted_date: Optional[datetime]
    application_deadline: Optional[datetime]
    closed_at: Optional[datetime] = None
    closed_reason: Optional[str] = None
    number_of_applications: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)



class JobListResponseSchema(BaseModel):
    rows: List[JobListGridRowSchema]
    page: int
    page_size: int
    total_records: int


class PostJobResponseSchema(BaseModel):
    total_applications_received: int = 0
    job_id: str
    employer_id: str
    job_title: str
    job_slug: str

    job_description: Optional[str] = None
    employment_type: Optional[str] = None
    experience_required: Optional[str] = None
    location: Optional[str] = None
    country_id: Optional[str] = None
    location_id: Optional[str] = None
    custom_city: Optional[str] = None
    work_mode: Optional[str] = None
    skills: List[str] = []
    salary_range: Optional[str] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    number_of_openings: Optional[int] = None
    application_deadline: Optional[datetime] = None
    company_name: Optional[str] = None
    contact_email: Optional[str] = None
    job_category: Optional[str] = None
    seniority_level: Optional[str] = None
    team: Optional[str] = None
    team_size: Optional[str] = None
    education: Optional[str] = None
    responsibilities: List[str] = []
    requirements: List[str] = []
    benefits: List[str] = []
    application_instructions: Optional[str] = None
    working_hours: Optional[str] = None
    office_location: Optional[str] = None
    map_url: Optional[str] = None
    status: str
    closed_at: Optional[datetime] = None
    closed_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj):
        def _value(name, default=None):
            return getattr(obj, name, default)

        def _range_value(min_value, max_value):
            if min_value is None and max_value is None:
                return None
            if min_value is None:
                return str(max_value)
            if max_value is None:
                return str(min_value)
            if min_value == max_value:
                return str(min_value)
            return f"{min_value}-{max_value}"

        def _skills():
            raw_skills = _value("skills", [])
            if not raw_skills:
                return []
            return [str(getattr(skill, "skill", skill)) for skill in raw_skills]

        def _make_utc_aware(dt):
            """If the datetime is naive, attach UTC timezone to prevent
            frontend timezone misinterpretation (which causes date shifts)."""
            if dt is None:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        return cls(
            total_applications_received=_value("total_applications_received", 0),
            job_id=_value("job_id"),
            employer_id=_value("employer_id"),
            job_title=_value("title", _value("job_title")),
            job_slug=slugify_job_title(_value("title", _value("job_title"))),
            job_description=_value("description", _value("job_description")),

            employment_type=_value("employment_type"),
            experience_required=_range_value(_value("experience_min"), _value("experience_max")),
            location=_value("location"),
            country_id=_value("country_id"),
            location_id=_value("location_id"),
            custom_city=_value("custom_city"),
            work_mode=_value("work_mode"),
            skills=_skills(),
            salary_range=_range_value(_value("salary_min"), _value("salary_max")),
            salary_currency=_value("salary_currency"),
            salary_period=_value("salary_period"),
            number_of_openings=_value("no_of_openings", _value("number_of_openings")),
            application_deadline=_make_utc_aware(_value("application_deadline")),
            company_name=_value("company_name"),
            contact_email=_value("contact_email"),
            job_category=_value("job_category"),
            seniority_level=_value("seniority_level"),
            team=_value("team"),
            team_size=_value("team_size"),
            education=_value("education"),
            responsibilities=list(_value("responsibilities", []) or []),
            requirements=list(_value("requirements", []) or []),
            benefits=list(_value("benefits", []) or []),
            application_instructions=_value("application_instructions"),
            working_hours=_value("working_hours"),
            office_location=_value("office_location"),
            map_url=_value("map_url"),
            status=_value("status"),
            closed_at=_value("closed_at"),
            closed_reason=_value("closed_reason"),
            created_at=posted_display_date(_value("created_at")),
            updated_at=_value("updated_at"),
            created_by=_value("created_by"),
            updated_by=_value("updated_by"),
        )


class CloseJobRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000, examples=["Position Filled"])

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        reason = str(value).strip()
        return reason or None


class CloseJobResponse(BaseModel):
    job_id: str
    status: str
    closed_at: datetime
    closed_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReopenJobResponseData(BaseModel):
    job_id: str
    status: str


class ReopenJobResponse(BaseModel):
    success: bool = True
    message: str = "Job reopened successfully."
    data: ReopenJobResponseData


