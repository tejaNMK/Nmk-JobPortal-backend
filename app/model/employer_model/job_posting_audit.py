from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime, Index, Integer, Text


class JobPostingAudit(SQLModel, table=True):
    """Audit log for job posting lifecycle events."""

    __tablename__ = "job_posting_audit"
    __table_args__ = (
        Index("idx_job_posting_audit_employer_id", "employer_id"),
        Index("idx_job_posting_audit_job_id", "job_id"),
        Index("idx_job_posting_audit_event_type", "event_type"),
    )

    audit_id: int = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True),
    )

    employer_id: str = Field(
        sa_column=Column(Text, nullable=False, index=True)
    )

    job_id: str = Field(
        sa_column=Column(Text, nullable=False, index=True)
    )

    event_type: str = Field(
        sa_column=Column(Text, nullable=False)
    )

    message: Optional[str] = Field(
        default=None,
        sa_column=Column(Text)
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False),
    )

    actor_user_id: Optional[str] = Field(
        default=None,
        sa_column=Column(Text)
    )

    actor_email: Optional[str] = Field(
        default=None,
        sa_column=Column(Text)
    )