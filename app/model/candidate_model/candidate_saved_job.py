from datetime import datetime
from typing import Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlmodel import Field, Relationship, SQLModel


class CandidateSavedJob(SQLModel, table=True):
    __tablename__ = "candidate_saved_jobs"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id"),
        Index("idx_candidate_saved_jobs_candidate", "candidate_id"),
    )

    saved_job_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    job_id: str = Field(sa_column=Column(Text, ForeignKey("jobs.job_id"), nullable=False))
    saved_flag: bool = Field(default=True, sa_column=Column(Boolean, server_default=text("true")))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    deleted_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))

    candidate: "CandidateProfile" = Relationship(back_populates="saved_jobs")
    job: "Job" = Relationship(back_populates="candidate_saved_jobs")
