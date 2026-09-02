from datetime import datetime
from decimal import Decimal
from typing import Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, text
from sqlmodel import Field, Relationship, SQLModel


class JobRecommendation(SQLModel, table=True):
    __tablename__ = "job_recommendations"

    recommendation_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    job_id: str = Field(sa_column=Column(Text, ForeignKey("jobs.job_id"), nullable=False))
    match_score: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))
    generated_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))

    candidate: "CandidateProfile" = Relationship(back_populates="job_recommendations")
    job: "Job" = Relationship(back_populates="job_recommendations")
