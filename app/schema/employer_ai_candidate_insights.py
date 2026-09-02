from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


AI_CANDIDATE_INSIGHTS_FEATURE_KEY = "ai_candidate_insights"
AI_CANDIDATE_INSIGHTS_MONTHLY_LIMIT_KEY = "ai_candidate_insights_per_month"
AI_CANDIDATE_INSIGHTS_PROMPT_VERSION = "candidate_ai_insights_v1"


class CandidateExperienceLevel(str, Enum):
    ENTRY = "ENTRY"
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"
    LEAD = "LEAD"
    EXECUTIVE = "EXECUTIVE"
    UNKNOWN = "UNKNOWN"


class CandidateAIConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CandidateAIInsightsSource(BaseModel):
    profile_used: bool = False
    resume_used: bool = False
    skills_used: bool = False
    experience_used: bool = False
    education_used: bool = False
    projects_used: bool = False
    certifications_used: bool = False


class CandidateAIInsightsMetadata(BaseModel):
    cached: bool = False
    stale: bool = False
    generated_at: Optional[datetime] = None
    model_id: Optional[str] = None
    prompt_version: str = AI_CANDIDATE_INSIGHTS_PROMPT_VERSION


class CandidateAIInsightsPayload(BaseModel):
    summary: str = Field(default="", max_length=1200)
    experience_level: CandidateExperienceLevel = CandidateExperienceLevel.UNKNOWN
    years_of_experience: float = Field(default=0, ge=0, le=80)
    confidence: CandidateAIConfidence = CandidateAIConfidence.LOW
    primary_skills: list[str] = Field(default_factory=list, max_length=12)
    key_strengths: list[str] = Field(default_factory=list, max_length=8)
    suitable_roles: list[str] = Field(default_factory=list, max_length=5)
    potential_gaps: list[str] = Field(default_factory=list, max_length=8)

    @field_validator(
        "primary_skills",
        "key_strengths",
        "suitable_roles",
        "potential_gaps",
        mode="before",
    )
    @classmethod
    def clean_string_lists(cls, values) -> list[str]:
        if values is None:
            values = []
        elif isinstance(values, str):
            values = [values]
        elif not isinstance(values, list):
            values = []
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            text = str(value or "").strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                cleaned.append(text[:240])
        return cleaned

    @field_validator("experience_level", mode="before")
    @classmethod
    def normalize_experience_level(cls, value):
        normalized = str(value or "UNKNOWN").strip().upper().replace(" ", "_")
        aliases = {
            "FRESHER": "ENTRY",
            "ENTRY_LEVEL": "ENTRY",
            "MID_LEVEL": "MID",
            "MIDDLE": "MID",
            "SENIOR_LEVEL": "SENIOR",
        }
        return aliases.get(normalized, normalized)

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value):
        normalized = str(value or "LOW").strip().upper()
        return normalized if normalized in CandidateAIConfidence.__members__ else "LOW"

    @field_validator("years_of_experience", mode="before")
    @classmethod
    def normalize_years(cls, value):
        try:
            years = float(value or 0)
        except (TypeError, ValueError):
            return 0
        return max(0, min(years, 80))


class CandidateAIInsightsResponse(CandidateAIInsightsPayload):
    metadata: CandidateAIInsightsMetadata = Field(default_factory=CandidateAIInsightsMetadata)
