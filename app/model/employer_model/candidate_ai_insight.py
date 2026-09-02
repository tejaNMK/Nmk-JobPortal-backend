from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class CandidateAIInsight(SQLModel, table=True):
    __tablename__ = "candidate_ai_insights"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_candidate_ai_insights_candidate"),
        Index("idx_candidate_ai_insights_candidate", "candidate_id"),
        Index("idx_candidate_ai_insights_hash", "candidate_data_hash"),
    )

    insight_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )
    candidate_id: str = Field(
        sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False)
    )
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    primary_skills: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    experience_level: str = Field(
        default="UNKNOWN",
        sa_column=Column(String(30), nullable=False, server_default=text("'UNKNOWN'")),
    )
    career_focus: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    key_strengths: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    potential_gaps: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    suitable_roles: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    notable_experience: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    education_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    certifications: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    years_of_experience: Optional[float] = Field(default=None, sa_column=Column(Float))
    confidence: str = Field(
        default="LOW",
        sa_column=Column(String(20), nullable=False, server_default=text("'LOW'")),
    )
    source_metadata: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    candidate_data_hash: str = Field(sa_column=Column(String(64), nullable=False))
    model_name: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    prompt_version: str = Field(sa_column=Column(String(60), nullable=False))
    generated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=utc_now_naive),
    )
