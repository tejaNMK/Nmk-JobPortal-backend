"""Schemas for the candidate-facing AI ATS resume analysis feature."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ATSResumeAnalysisRequest(BaseModel):
    """Analyze the candidate's saved resume data or one of their uploaded CVs."""

    resume_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Optional ID of the candidate-owned uploaded resume to parse and analyze. Defaults to the latest saved resume data.",
    )
    job_description: Optional[str] = Field(
        default=None,
        max_length=15000,
        description="Optional job description used for a separate job-specific ATS comparison.",
    )

    @field_validator("resume_id")
    @classmethod
    def resume_id_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("resume_id must not be blank")
        return value.strip() if value else None

    @field_validator("job_description")
    @classmethod
    def job_description_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("job_description must not be blank")
        return value.strip() if value else None


class ATSScoreBreakdown(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    keyword_skill_match_score: int = Field(ge=0, le=100)
    experience_relevance_score: int = Field(ge=0, le=100)
    resume_structure_formatting_score: int = Field(ge=0, le=100)
    content_quality_score: int = Field(ge=0, le=100)


class ATSGeneralAnalysis(BaseModel):
    """ATS assessment based only on the candidate's resume."""

    scores: ATSScoreBreakdown
    detected_skills: list[str] = Field(default_factory=list)
    detected_roles: list[str] = Field(default_factory=list)
    missing_keywords_or_skills: list[str] = Field(default_factory=list)
    detected_issues: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)


class ATSJobSpecificAnalysis(BaseModel):
    """Additional assessment produced only when a job description is supplied."""

    job_specific_score: int = Field(ge=0, le=100)
    matched_keywords_or_skills: list[str] = Field(default_factory=list)
    missing_keywords_or_skills: list[str] = Field(default_factory=list)
    experience_relevance_score: int = Field(ge=0, le=100)
    detected_issues: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)


class ATSResumeAnalysisResponse(BaseModel):
    """Structured, candidate-safe ATS analysis; no provider metadata or prompts."""

    general_analysis: ATSGeneralAnalysis
    job_specific_analysis: Optional[ATSJobSpecificAnalysis] = None

    model_config = ConfigDict(from_attributes=True)
