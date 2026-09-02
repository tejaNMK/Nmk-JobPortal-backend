from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Composite weights — must sum to 100. Named constants (mirroring
# `app.service.candidate_job_recommendation_engine`'s WEIGHT_* convention) so
# the "why" behind the overall score is explainable and easy to tune without
# touching the scoring logic itself.
#
# Two of the five factors (skills, experience) come from the same
# deterministic engine that already powers Job Recommendations and the
# Skill Match API; Profile Completeness reuses the value already maintained
# on `CandidateProfile.profile_completion_pct`. Resume Match and Interview
# Readiness have no existing deterministic engine, so they are AI-generated
# (see `ApplicationReadinessService`).
# ---------------------------------------------------------------------------
WEIGHT_RESUME_MATCH = 25
WEIGHT_SKILLS_MATCH = 25
WEIGHT_EXPERIENCE_MATCH = 20
WEIGHT_PROFILE_COMPLETENESS = 15
WEIGHT_INTERVIEW_READINESS = 15

TOTAL_READINESS_WEIGHT = (
    WEIGHT_RESUME_MATCH
    + WEIGHT_SKILLS_MATCH
    + WEIGHT_EXPERIENCE_MATCH
    + WEIGHT_PROFILE_COMPLETENESS
    + WEIGHT_INTERVIEW_READINESS
)
assert TOTAL_READINESS_WEIGHT == 100, "Application Readiness weights must sum to 100"


class ApplicationReadinessScoreResponse(BaseModel):
    """AI Application Readiness Score API response.

    Combines deterministic scoring already used elsewhere in the codebase
    (skills + experience fit from `candidate_job_recommendation_engine`,
    profile completeness from `CandidateProfile.profile_completion_pct`)
    with two AI-generated (AWS Bedrock, via `app.service.ai_service.AIService`)
    factors that have no existing deterministic engine: Resume Match and
    Interview Readiness. `overall_score` is a deterministic weighted
    composite of the five factors below (see `application_readiness.py`
    WEIGHT_* constants) -- it is never itself AI-generated, so it can't
    drift from the sub-scores it is computed from.
    """

    job_id: str
    job_title: str

    overall_score: float = Field(
        ge=0,
        le=100,
        description="Weighted composite of the five factor scores below (0-100).",
    )

    resume_match_score: float = Field(
        ge=0,
        le=100,
        description="AI-assessed alignment between the candidate's resume content and this job (0-100).",
    )
    skills_match_score: float = Field(
        ge=0,
        le=100,
        description=(
            "Deterministic skill-set overlap between the candidate and this "
            "job's required/preferred skills, from the same engine that "
            "powers the Skill Match API (0-100)."
        ),
    )
    experience_match_score: float = Field(
        ge=0,
        le=100,
        description=(
            "Deterministic fit between the candidate's total experience and "
            "this job's experience range, from the same engine that powers "
            "Job Recommendations (0-100)."
        ),
    )
    profile_completeness_score: float = Field(
        ge=0,
        le=100,
        description="The candidate's existing profile completion percentage (0-100).",
    )
    interview_readiness_score: float = Field(
        ge=0,
        le=100,
        description="AI-assessed readiness for an interview for this job, based on profile/resume depth (0-100).",
    )

    matched_skills: List[str] = Field(
        default_factory=list,
        description="Skills the candidate has that this job also lists (required or preferred).",
    )
    missing_skills: List[str] = Field(
        default_factory=list,
        description="Required or preferred skills on the job the candidate's profile/resume does not show.",
    )

    strengths: List[str] = Field(
        default_factory=list,
        description="Candidate strengths relevant to this job, per the AI analysis.",
    )
    weaknesses: List[str] = Field(
        default_factory=list,
        description="Candidate gaps or weaknesses relevant to this job, per the AI analysis.",
    )
    gaps: List[str] = Field(
        default_factory=list,
        description=(
            "Non-skill readiness gaps identified by the AI analysis -- e.g. "
            "thin resume detail, missing certifications, or interview "
            "preparation gaps. Skill gaps are covered by `missing_skills`."
        ),
    )
    improvement_suggestions: List[str] = Field(
        default_factory=list,
        description="Concrete, actionable suggestions for the candidate to improve their readiness for this job.",
    )

    readiness_explanation: str = Field(
        default="",
        description="A concise, human-readable explanation of the overall readiness score.",
    )

    model_config = ConfigDict(from_attributes=True)