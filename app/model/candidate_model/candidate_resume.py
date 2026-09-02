from datetime import datetime
from typing import List, Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlmodel import Field, Relationship, SQLModel


class CandidateResume(SQLModel, table=True):
    __tablename__ = "candidate_resumes"
    __table_args__ = (Index("idx_candidate_resumes_candidate", "candidate_id"),)

    resume_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    candidate_id: str = Field(sa_column=Column(Text, ForeignKey("candidate_profiles.candidate_id"), nullable=False))
    version_no: int = Field(default=1, sa_column=Column(Integer, server_default=text("1")))
    file_name: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    file_path: Optional[str] = Field(default=None, sa_column=Column(Text))
    blob_ref: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Size of the uploaded file in bytes, captured at upload time. NULL for
    # rows created before this field existed. Powers the "file size" shown
    # on the Download CV page before the candidate downloads a version.
    file_size: Optional[int] = Field(default=None, sa_column=Column(Integer))
    # SHA-256 digest of the uploaded bytes, used to detect and reject a
    # duplicate upload of the same file (regardless of what it's named).
    # NULL for rows created before this field existed.
    file_hash: Optional[str] = Field(default=None, sa_column=Column(String(64)))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, server_default=text("true")))

    # ── Resume Library (Manage Resume / Download CV pages) ──
    version_name: Optional[str] = Field(default=None, sa_column=Column(Text))
    # NOTE: template is a user-chosen label (set via the "Version Controls"
    # form / update_resume) and must stay unset until the candidate actually
    # picks one. It must NOT default to "Minimal ATS" — that previously made
    # every freshly uploaded resume (which has no template at all) look like
    # it was assigned the "Minimal ATS" template.
    template: Optional[str] = Field(default=None, sa_column=Column(Text))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    usage_note: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_archived: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))
    download_count: int = Field(default=0, sa_column=Column(Integer, server_default=text("0")))
    share_token: Optional[str] = Field(default=None, sa_column=Column(Text, unique=True))
    share_enabled: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))
    share_requires_email: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))
    share_expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    share_view_count: int = Field(default=0, sa_column=Column(Integer, server_default=text("0")))

    uploaded_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    updated_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=utc_now_naive))
    created_by: Optional[str] = Field(default=None, sa_column=Column(Text))
    updated_by: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_deleted: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))
    deleted_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))

    candidate: "CandidateProfile" = Relationship(back_populates="resumes")
    applications: List["JobApplication"] = Relationship(back_populates="resume")