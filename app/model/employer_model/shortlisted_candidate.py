from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, text
from sqlmodel import Field, SQLModel


class ShortlistedCandidate(SQLModel, table=True):
    __tablename__ = "shortlisted_candidates"
    __table_args__ = (Index("idx_shortlisted_candidate", "candidate_id"),)

    shortlist_id: str = Field(sa_column=Column(Text, primary_key=True, nullable=False))
    employer_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("employer_profiles.id"),
            nullable=False,
        )
    )
    recruiter_id: Optional[str] = Field(default=None, sa_column=Column(Text))
    candidate_id: str = Field(sa_column=Column(Text, nullable=False))
    job_id: str = Field(
        sa_column=Column(Text, ForeignKey("jobs.job_id"), nullable=False)
    )
    shortlisted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
    status: Optional[str] = Field(
        default="ACTIVE",
        sa_column=Column(Text, server_default=text("'ACTIVE'")),
    )
    remarks: Optional[str] = Field(default=None, sa_column=Column(Text))
