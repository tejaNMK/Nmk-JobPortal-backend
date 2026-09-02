
from datetime import date, datetime
from typing import List, Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Index, String, Text, text
from sqlmodel import Field, Relationship, SQLModel


class JobApplication(SQLModel, table=True):
    __tablename__ = "job_applications"
    __table_args__ = (
        Index("idx_job_applications_candidate", "candidate_id"),
        Index("idx_job_applications_job", "job_id"),
    )

    application_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    job_id: str = Field(sa_column=Column(Text, ForeignKey("jobs.job_id"), nullable=False))
    resume_id: Optional[str] = Field(default=None, sa_column=Column(Text, ForeignKey("candidate_resumes.resume_id")))
    resume_file_name_snapshot: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    resume_blob_ref_snapshot: Optional[str] = Field(default=None, sa_column=Column(Text))
    resume_file_path_snapshot: Optional[str] = Field(default=None, sa_column=Column(Text))
    resume_file_size_snapshot: Optional[int] = Field(default=None, sa_column=Column(Integer))
    application_status: str = Field(default="APPLIED", sa_column=Column(String(50), server_default=text("'APPLIED'")))
    cover_letter_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    recruiter_notes_ref: Optional[str] = Field(default=None, sa_column=Column(Text))
    recruiter_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    source: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    applied_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    updated_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=utc_now_naive))
    created_by: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Columns referenced by schema/service but previously missing from the model
    referral_contact: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    next_step_text: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    next_step_due: Optional[date] = Field(default=None, sa_column=Column(Date))
    interview_loop_date: Optional[date] = Field(default=None, sa_column=Column(Date))
    candidate_rating: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer)
    )
    shortlisted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime)
    )
    
    is_deleted: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))
    deleted_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))

    candidate: "CandidateProfile" = Relationship(back_populates="applications")
    job: "Job" = Relationship(back_populates="applications")
    resume: Optional["CandidateResume"] = Relationship(back_populates="applications")
    notes: List["ApplicationNote"] = Relationship(back_populates="application")
    status_history: List["ApplicationStatusHistory"] = Relationship(back_populates="application")
    interviews: List["Interview"] = Relationship(back_populates="application")

