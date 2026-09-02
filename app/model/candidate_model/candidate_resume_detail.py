from datetime import datetime
from typing import Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


class CandidateResumeDetail(SQLModel, table=True):
    __tablename__ = "candidate_resume_details"

    resume_detail_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    education_json: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    experience_json: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    skills_json: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    certifications_json: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    projects_json: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    languages_json: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    generated_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    is_deleted: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))

    candidate: "CandidateProfile" = Relationship(back_populates="resume_details")