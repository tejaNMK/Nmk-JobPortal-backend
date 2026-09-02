from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class SkillMatchResponse(BaseModel):
    """API-AI-002 — SkillMatchAPI response.

    Compares the logged-in candidate's skills (profile + latest resume)
    against a single job's required/preferred skills.
    """

    job_id: str
    job_title: str

    match_percentage: float = Field(
        description="0-100 skill compatibility between the candidate and this job."
    )

    matched_skills: List[str] = Field(
        default_factory=list,
        description="Skills the candidate has that this job also lists (required or preferred).",
    )
    missing_required_skills: List[str] = Field(
        default_factory=list,
        description="Required skills on the job the candidate's profile/resume does not list.",
    )
    missing_preferred_skills: List[str] = Field(
        default_factory=list,
        description="Preferred (nice-to-have) skills on the job the candidate does not list.",
    )
    extra_skills: List[str] = Field(
        default_factory=list,
        description="Candidate skills not called out by this job — useful for resume/profile tips.",
    )

    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)