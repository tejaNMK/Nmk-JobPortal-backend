from __future__ import annotations

import re
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.schema.job import MAX_JOB_DESCRIPTION_LENGTH


AI_JOB_DESCRIPTION_FEATURE_KEY = "ai_job_description_generator"
AI_JOB_DESCRIPTION_MONTHLY_LIMIT_KEY = "ai_job_description_generations_per_month"
MAX_AI_INPUT_CHARS = 8000
MAX_AI_LIST_ITEMS = 20
MAX_AI_LIST_ITEM_CHARS = 300
MAX_ADDITIONAL_INSTRUCTIONS_CHARS = 1000
MAX_KEYWORDS = 30

WorkplaceType = Literal["REMOTE", "HYBRID", "ONSITE"]
TextItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_AI_LIST_ITEM_CHARS),
]


def normalize_workplace_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if normalized == "ON_SITE":
        normalized = "ONSITE"
    return normalized


def reject_unsafe_input(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    if not text:
        return None
    unsafe_patterns = (
        r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions",
        r"disregard\s+(all\s+)?(previous|above|prior)\s+instructions",
        r"reveal\s+(the\s+)?(system|developer)\s+prompt",
        r"print\s+(the\s+)?(api\s+key|secret|token)",
    )
    lowered = text.lower()
    if any(re.search(pattern, lowered) for pattern in unsafe_patterns):
        raise ValueError("Input contains unsafe instructions")
    return text


def normalize_text_list(value: list[str] | None, field_label: str) -> list[str] | None:
    if value is None:
        return None
    if len(value) > MAX_AI_LIST_ITEMS:
        raise ValueError(f"{field_label} can contain at most {MAX_AI_LIST_ITEMS} items")
    normalized = [reject_unsafe_input(item) for item in value]
    normalized = [item for item in normalized if item]
    return normalized or None


class AIJobDescriptionGenerateRequest(BaseModel):
    job_id: Optional[str] = Field(default=None, max_length=100)
    section: Optional[str] = Field(default=None, min_length=1, max_length=100)
    job_title: str = Field(..., min_length=1, max_length=100)
    company_name: Optional[str] = Field(default=None, max_length=150)
    company_description: Optional[str] = Field(default=None, max_length=2000)
    department: Optional[str] = Field(default=None, max_length=150)
    industry: Optional[str] = Field(default=None, max_length=150)
    employment_type: Optional[str] = Field(default=None, max_length=50)
    workplace_type: Optional[WorkplaceType] = None
    location: Optional[str] = Field(default=None, max_length=150)
    education: Optional[str] = Field(default=None, max_length=300)
    experience: Optional[str] = Field(default=None, max_length=100)
    minimum_experience: Optional[int] = Field(default=None, ge=0, le=60)
    maximum_experience: Optional[int] = Field(default=None, ge=0, le=60)
    salary: Optional[str] = Field(default=None, max_length=200)
    required_skills: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    skills: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    preferred_skills: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    qualifications: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    required_qualifications: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    preferred_qualifications: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    responsibilities: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    benefits: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    visa_sponsorship: Optional[str] = Field(default=None, max_length=100)
    shift: Optional[str] = Field(default=None, max_length=100)
    languages: Optional[list[TextItem]] = Field(default=None, max_length=MAX_AI_LIST_ITEMS)
    job_category: Optional[str] = Field(default=None, max_length=150)
    keywords: Optional[list[TextItem]] = Field(default=None, max_length=MAX_KEYWORDS)
    tone: Optional[str] = Field(default="professional", max_length=50)
    output_language: Optional[str] = Field(default="English", max_length=80)
    additional_instructions: Optional[str] = Field(
        default=None,
        max_length=MAX_ADDITIONAL_INSTRUCTIONS_CHARS,
    )

    @field_validator("workplace_type", mode="before")
    @classmethod
    def normalize_workplace(cls, value):
        return normalize_workplace_type(value)

    @field_validator(
        "job_id",
        "section",
        "job_title",
        "company_name",
        "company_description",
        "department",
        "industry",
        "employment_type",
        "location",
        "education",
        "experience",
        "salary",
        "visa_sponsorship",
        "shift",
        "job_category",
        "tone",
        "output_language",
        "additional_instructions",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value):
        return reject_unsafe_input(value)

    @field_validator("required_skills")
    @classmethod
    def validate_required_skills(cls, value):
        return normalize_text_list(value, "Required skills")

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value):
        return normalize_text_list(value, "Skills")

    @field_validator("preferred_skills")
    @classmethod
    def validate_preferred_skills(cls, value):
        return normalize_text_list(value, "Preferred skills")

    @field_validator("qualifications")
    @classmethod
    def validate_qualifications(cls, value):
        return normalize_text_list(value, "Qualifications")

    @field_validator("required_qualifications")
    @classmethod
    def validate_required_qualifications(cls, value):
        return normalize_text_list(value, "Required qualifications")

    @field_validator("preferred_qualifications")
    @classmethod
    def validate_preferred_qualifications(cls, value):
        return normalize_text_list(value, "Preferred qualifications")

    @field_validator("responsibilities")
    @classmethod
    def validate_responsibilities(cls, value):
        return normalize_text_list(value, "Responsibilities")

    @field_validator("benefits")
    @classmethod
    def validate_benefits(cls, value):
        return normalize_text_list(value, "Benefits")

    @field_validator("languages")
    @classmethod
    def validate_languages(cls, value):
        return normalize_text_list(value, "Languages")

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value):
        return normalize_text_list(value, "Keywords")

    @model_validator(mode="after")
    def validate_rules(self):
        self.job_title = reject_unsafe_input(self.job_title) or ""
        if not self.job_title:
            raise ValueError("Job title is required for generation")
        if (
            self.minimum_experience is not None
            and self.maximum_experience is not None
            and self.minimum_experience > self.maximum_experience
        ):
            raise ValueError("Minimum experience cannot exceed maximum experience")
        if self.salary and re.search(r"\d", self.salary):
            amounts = [int(part.replace(",", "")) for part in re.findall(r"\d[\d,]*", self.salary)]
            if len(amounts) >= 2 and amounts[0] > amounts[1]:
                raise ValueError("Salary range minimum cannot exceed maximum")
        if len(self.model_dump_json(exclude_none=True)) > MAX_AI_INPUT_CHARS:
            raise ValueError(f"AI generation input must not exceed {MAX_AI_INPUT_CHARS} characters")
        return self


class AIJobDescriptionImproveRequest(BaseModel):
    job_id: Optional[str] = Field(default=None, max_length=100)
    section: Optional[str] = Field(default=None, min_length=1, max_length=100)
    existing_description: str = Field(
        ...,
        min_length=1,
        max_length=MAX_JOB_DESCRIPTION_LENGTH,
    )
    tone: Optional[str] = Field(default="professional", max_length=50)
    length: Optional[str] = Field(default="1000-1500 words", max_length=80)
    industry: Optional[str] = Field(default=None, max_length=150)
    additional_instructions: Optional[str] = Field(
        default=None,
        max_length=MAX_ADDITIONAL_INSTRUCTIONS_CHARS,
    )

    @field_validator(
        "job_id",
        "section",
        "existing_description",
        "tone",
        "length",
        "industry",
        "additional_instructions",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value):
        return reject_unsafe_input(value)

    @model_validator(mode="after")
    def validate_rules(self):
        if not self.existing_description:
            raise ValueError("Existing description is required for improvement")
        if len(self.model_dump_json(exclude_none=True)) > MAX_AI_INPUT_CHARS:
            raise ValueError(f"AI improvement input must not exceed {MAX_AI_INPUT_CHARS} characters")
        return self


class AIJobDescriptionRegenerateRequest(BaseModel):
    job_id: Optional[str] = Field(default=None, max_length=100)
    section: str = Field(..., min_length=1, max_length=100)
    existing_description: str = Field(..., min_length=1, max_length=MAX_JOB_DESCRIPTION_LENGTH)
    instructions: Optional[str] = Field(default=None, max_length=MAX_ADDITIONAL_INSTRUCTIONS_CHARS)
    tone: Optional[str] = Field(default="professional", max_length=50)

    @field_validator("job_id", "section", "existing_description", "instructions", "tone", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return reject_unsafe_input(value)


class AIUsageSchema(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: int = 0
    cost_estimate_usd: float = 0.0


class AIJobDescriptionSectionItemsPayload(BaseModel):
    items: list[str] = Field(..., min_length=1, max_length=50)


class AIJobDescriptionSectionTextPayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class AIJobDescriptionSectionResponse(BaseModel):
    section: str
    content: list[str] | str
    generated_description: str
    usage: AIUsageSchema = Field(default_factory=AIUsageSchema)


class AIJobDescriptionStructuredPayload(BaseModel):
    title: str = ""
    companyOverview: str = ""
    roleSummary: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    requiredSkills: list[str] = Field(default_factory=list)
    preferredSkills: list[str] = Field(default_factory=list)
    requiredQualifications: list[str] = Field(default_factory=list)
    preferredQualifications: list[str] = Field(default_factory=list)
    technicalSkills: list[str] = Field(default_factory=list)
    softSkills: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    perks: list[str] = Field(default_factory=list)
    workEnvironment: str = ""
    careerGrowth: str = ""
    salaryInformation: str = ""
    equalOpportunityStatement: str = ""
    applicationProcess: str = ""
    keywords: list[str] = Field(default_factory=list)
    atsOptimizedSummary: str = ""
    atsScore: int = Field(default=0, ge=0, le=100)
    markdown: str = ""
    html: str = ""


class AIJobDescriptionResponse(BaseModel):
    generated_description: str
    title: str = ""
    companyOverview: str = ""
    roleSummary: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    requiredSkills: list[str] = Field(default_factory=list)
    preferredSkills: list[str] = Field(default_factory=list)
    requiredQualifications: list[str] = Field(default_factory=list)
    preferredQualifications: list[str] = Field(default_factory=list)
    technicalSkills: list[str] = Field(default_factory=list)
    softSkills: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    perks: list[str] = Field(default_factory=list)
    workEnvironment: str = ""
    careerGrowth: str = ""
    salaryInformation: str = ""
    equalOpportunityStatement: str = ""
    applicationProcess: str = ""
    keywords: list[str] = Field(default_factory=list)
    atsOptimizedSummary: str = ""
    atsScore: int = Field(default=0, ge=0, le=100)
    markdown: str = ""
    html: str = ""
    usage: AIUsageSchema = Field(default_factory=AIUsageSchema)
