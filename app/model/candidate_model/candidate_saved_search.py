from datetime import datetime
from decimal import Decimal
from typing import Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text, text
from sqlmodel import Field, Relationship, SQLModel


class CandidateSavedSearch(SQLModel, table=True):
    __tablename__ = "candidate_saved_searches"

    saved_search_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    search_name: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    keywords: Optional[str] = Field(default=None, sa_column=Column(Text))
    skills: Optional[str] = Field(default=None, sa_column=Column(Text))
    location: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    work_mode: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    salary_min: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2)))
    salary_max: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2)))
    experience_min: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))
    experience_max: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    updated_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=utc_now_naive))

    candidate: "CandidateProfile" = Relationship(back_populates="saved_searches")
