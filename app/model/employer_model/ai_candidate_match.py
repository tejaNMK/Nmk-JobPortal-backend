from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class AICandidateMatch(SQLModel, table=True):
    __tablename__ = "ai_candidate_matches"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_id", name="uq_ai_candidate_matches_job_candidate"),
        Index("idx_ai_candidate_matches_job_score", "job_id", "overall_score"),
        Index("idx_ai_candidate_matches_candidate", "candidate_id"),
        Index("idx_ai_candidate_matches_source", "source_type"),
    )

    match_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )
    job_id: str = Field(sa_column=Column(Text, ForeignKey("jobs.job_id"), nullable=False))
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    application_id: Optional[str] = Field(default=None, sa_column=Column(Text, ForeignKey("job_applications.application_id")))

    source_type: str = Field(default="AI Recommended Candidate", sa_column=Column(String(40), nullable=False))
    overall_score: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default=text("0")))
    skills_score: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default=text("0")))
    experience_score: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default=text("0")))
    title_domain_score: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default=text("0")))
    education_score: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default=text("0")))
    location_score: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default=text("0")))
    preferred_skills_score: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default=text("0")))
    semantic_score: float = Field(default=0, sa_column=Column(Float, nullable=False, server_default=text("0")))

    matched_skills: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")))
    missing_required_skills: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")))
    matched_preferred_skills: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")))
    strengths: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")))
    gaps: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")))
    hard_requirements: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")))
    preferred_requirements: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")))
    semantic_signals: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")))

    ai_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    recommendation: str = Field(default="Review Manually", sa_column=Column(String(40), nullable=False, server_default=text("'Review Manually'")))
    scoring_version: str = Field(sa_column=Column(String(40), nullable=False))
    job_updated_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    candidate_updated_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    resume_generated_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))

    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")))
    updated_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=utc_now_naive))
