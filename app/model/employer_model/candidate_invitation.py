from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, text
from sqlmodel import Field, Relationship, SQLModel


class CandidateInvitation(SQLModel, table=True):
    """Employer -> Candidate invitation to apply.

    Business rules:
    - Employer owns the job
    - Candidate profile must be public/searchable (handled in service)
    - Prevent duplicate ACTIVE/PENDING invitations per (employer_id, candidate_id, job_id)
    """

    __tablename__ = "candidate_invitations"
    __table_args__ = (
        Index("idx_candidate_invitations_employer", "employer_id"),
        Index("idx_candidate_invitations_candidate", "candidate_id"),
        Index("idx_candidate_invitations_job", "job_id"),
        Index("idx_candidate_invitations_status", "status"),
        Index("idx_candidate_invitations_created_at", "created_at"),
    )

    invitation_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(Text, primary_key=True, nullable=False,
                         server_default=text("replace(gen_random_uuid()::text, '-', '')")),
    )

    employer_id: str = Field(sa_column=Column(Text, ForeignKey("employer_profiles.id"), nullable=False))
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    job_id: str = Field(sa_column=Column(Text, ForeignKey("jobs.job_id"), nullable=False))

    custom_message: Optional[str] = Field(default=None, sa_column=Column(Text))

    status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False, server_default=text("'PENDING'")),
    )

    invited_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    viewed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    responded_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    accepted_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    rejected_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=utc_now_naive),
    )

    # Relationships not strictly required, but helps selectinload if needed
    # (kept minimal to avoid extra joins).


