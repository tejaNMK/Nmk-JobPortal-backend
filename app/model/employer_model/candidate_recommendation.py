from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class CandidateRecommendation(SQLModel, table=True):
    __tablename__ = "candidate_recommendations"

    recommendation_id: str = Field(
        sa_column=Column(Text, primary_key=True, nullable=False)
    )
    employer_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("employer_profiles.id"),
            nullable=False,
        )
    )
    candidate_id: str = Field(sa_column=Column(Text, nullable=False))
    job_id: str = Field(
        sa_column=Column(Text, ForeignKey("jobs.job_id"), nullable=False)
    )
    application_id: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, ForeignKey("job_applications.application_id")),
    )
    match_score: Optional[float] = Field(default=None, sa_column=Column(Float))
    deterministic_score: Optional[float] = Field(default=None, sa_column=Column(Float))
    semantic_score: Optional[float] = Field(default=None, sa_column=Column(Float))
    match_label: Optional[str] = Field(default=None, sa_column=Column(Text))
    match_reasons: Optional[list] = Field(default=None, sa_column=Column(JSONB))
    missing_requirements: Optional[list] = Field(default=None, sa_column=Column(JSONB))
    score_breakdown: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    job_updated_at_snapshot: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    candidate_updated_at_snapshot: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    resume_detail_generated_at_snapshot: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    generated_at: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, server_default=text("CURRENT_TIMESTAMP")),
    )
