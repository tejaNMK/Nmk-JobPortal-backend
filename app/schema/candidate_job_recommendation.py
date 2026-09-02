from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CandidateRecommendedJobCardResponse(BaseModel):
    """A job card enriched with AI match information."""

    job_id: str
    job_title: str
    job_slug: str
    description_preview: Optional[str] = Field(
        default=None,
        description="Plain-text job description preview, capped at 120 characters.",
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
    posted_date: Optional[datetime] = None

    skills: List[str] = []
    is_saved: bool = False
    already_applied: bool = False
    application_status: Optional[str] = None

    # AI recommendation specific fields
    match_score: float = Field(
        description="Overall compatibility score between 0 and 100."
    )
    match_percentage: int = Field(
        description="match_score rounded to the nearest whole percentage, for display."
    )
    match_reasons: List[str] = Field(
        default_factory=list,
        description="Short, human-readable reasons this job was recommended.",
    )

    model_config = ConfigDict(from_attributes=True)


class CandidateRecommendedJobsResponse(BaseModel):
    total_records: int
    page: int
    page_size: int
    generated_at: Optional[datetime] = None
    results: List[CandidateRecommendedJobCardResponse] = []