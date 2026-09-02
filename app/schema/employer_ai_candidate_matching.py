from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


AI_CANDIDATE_MATCHING_FEATURE_KEY = "ai_candidate_matching"
AI_CANDIDATE_MATCHING_RUN_LIMIT_KEY = "ai_candidate_matching_runs_per_month"
AI_CANDIDATE_ANALYSIS_LIMIT_KEY = "ai_candidate_analyses_per_month"

MatchScope = Literal["applicants", "discovery", "all"]
MatchSource = Literal["Applicant", "AI Recommended Candidate"]


class AICandidateMatchRunRequest(BaseModel):
    scope: MatchScope = "applicants"
    min_score: Optional[float] = Field(default=None, ge=0, le=100)
    candidate_limit: int = Field(default=500, ge=1, le=2000)


class AICandidateMatchFilters(BaseModel):
    min_score: Optional[float] = Field(default=None, ge=0, le=100)
    skills: list[str] = Field(default_factory=list)
    experience_min: Optional[float] = Field(default=None, ge=0)
    experience_max: Optional[float] = Field(default=None, ge=0)
    location: Optional[str] = None
    education: Optional[str] = None
    availability: Optional[str] = None
    candidate_status: Optional[str] = None
    applied: Optional[bool] = None
    invited: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ExperienceMatch(BaseModel):
    candidate_years: Optional[float] = None
    required_years: Optional[int] = None
    maximum_years: Optional[int] = None
    score: float


class CandidateMatchResult(BaseModel):
    candidate_id: str
    candidate_name: str
    profile_image_url: Optional[str] = None
    match_score: int
    match_level: str
    source_type: MatchSource
    application_id: Optional[str] = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    matched_preferred_skills: list[str] = Field(default_factory=list)
    experience_match: ExperienceMatch
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    ai_summary: Optional[str] = None
    recommendation: str
    is_stale: bool = False
    generated_at: datetime


class CandidateMatchDetail(CandidateMatchResult):
    hard_requirements: dict = Field(default_factory=dict)
    preferred_requirements: dict = Field(default_factory=dict)
    semantic_signals: dict = Field(default_factory=dict)
    scoring_version: str


class AICandidateMatchRunResponse(BaseModel):
    job_id: str
    total_candidates_considered: int
    total_matches_generated: int
    scoring_version: str
    cached: bool = False
    items: list[CandidateMatchResult] = Field(default_factory=list)


class AICandidateMatchListResponse(BaseModel):
    job_id: str
    page: int
    page_size: int
    total_records: int
    items: list[CandidateMatchResult] = Field(default_factory=list)
