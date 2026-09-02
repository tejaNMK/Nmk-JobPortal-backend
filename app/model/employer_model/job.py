from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.model.candidate_model.candidate_saved_job import CandidateSavedJob
    from app.model.candidate_model.job_application import JobApplication
    from app.model.candidate_model.job_recommendation import JobRecommendation
    from app.model.employer_model.job_skill import JobSkill


class Job(SQLModel, table=True):
    """Job entity table for storing employer job postings."""

    __tablename__ = "jobs"

    __table_args__ = (

        # ── Indexes ──────────────────────────────────────────
        Index("idx_jobs_employer", "employer_id"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_location", "location"),
        Index("idx_jobs_employer_status", "employer_id", "status"),
        Index(
            "idx_jobs_active_employer_status_created_at",
            "employer_id",
            "status",
            "created_at",
            postgresql_where=text("is_deleted IS FALSE"),
        ),
        Index("idx_jobs_created_at", "created_at"),

        Index(
            "idx_jobs_employer_idempotency",
            "employer_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),

        # ── Check Constraints ─────────────────────────────────────────

        CheckConstraint(
            "experience_min >= 0",
            name="chk_experience_min_positive",
        ),
        CheckConstraint(
            "experience_max >= experience_min",
            name="chk_experience_range",
        ),
        CheckConstraint(
            "salary_min >= 0",
            name="chk_salary_min_positive",
        ),
        CheckConstraint(
            "salary_max >= salary_min",
            name="chk_salary_range",
        ),
        CheckConstraint(
            "no_of_openings > 0",
            name="chk_openings_positive",
        ),
    )

    # ── Primary Key ──────────────────────────────────────────────────────────
    job_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
        ),
    )

    # ── Employer Information ─────────────────────────────────────────────────
    employer_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("employer_profiles.id"),
            nullable=False,
            index=True,
        ),
    )

    title: str = Field(sa_column=Column(Text, nullable=False))

    description: str = Field(sa_column=Column(Text, nullable=False))

    employment_type: str = Field(sa_column=Column(Text, nullable=False))

    experience_min: Optional[int] = Field(default=None, sa_column=Column(Integer))

    experience_max: Optional[int] = Field(default=None, sa_column=Column(Integer))

    location: Optional[str] = Field(default=None, sa_column=Column(Text))

    country_id: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, ForeignKey("master_countries.country_id")),
    )

    location_id: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, ForeignKey("master_locations.location_id")),
    )

    custom_city: Optional[str] = Field(default=None, sa_column=Column(Text))

    work_mode: Optional[str] = Field(default=None, sa_column=Column(Text))

    salary_min: Optional[float] = Field(default=None, sa_column=Column(Float))

    salary_max: Optional[float] = Field(default=None, sa_column=Column(Float))

    salary_currency: str = Field(
        default="USD",
        sa_column=Column(String(10), nullable=False, server_default=text("'USD'")),
    )

    salary_period: str = Field(
        default="Monthly",
        sa_column=Column(String(20), nullable=False, server_default=text("'Monthly'")),
    )

    no_of_openings: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default=text("1")),
    )

    application_deadline: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))

    # ── Job Status ───────────────────────────────────────────────────────────
    status: str = Field(
        default="DRAFT",
        sa_column=Column(
            Text,
            nullable=False,
            server_default=text("'DRAFT'"),
        ),
    )

    # ── Job Copy Tracking ────────────────────────────────────────────────────
    copied_from_job_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            Text,
            ForeignKey("jobs.job_id"),
        ),
    )

    # ── Job Closing Information ──────────────────────────────────────────────
    closed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    closed_reason: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    # ── Audit Columns ────────────────────────────────────────────────────────
    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=utc_now_naive,
        ),
    )

    created_by: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    updated_by: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    # ── Soft Delete Support ──────────────────────────────────────────────────
    is_deleted: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
    )

    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    # ── Optimistic Locking ───────────────────────────────────────────────────
    version: int = Field(
        default=0,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("0"),
        ),
    )

    # ── Post Job Fields ──────────────────────────────────────────────────────
    company_name: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    team: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    job_category: Optional[str] = Field(default=None, sa_column=Column(Text))

    seniority_level: Optional[str] = Field(default=None, sa_column=Column(Text))

    team_size: Optional[str] = Field(default=None, sa_column=Column(Text))

    education: Optional[str] = Field(default=None, sa_column=Column(Text))

    responsibilities: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))

    requirements: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))

    benefits: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))

    application_instructions: Optional[str] = Field(default=None, sa_column=Column(Text))

    working_hours: Optional[str] = Field(default=None, sa_column=Column(Text))

    office_location: Optional[str] = Field(default=None, sa_column=Column(Text))

    map_url: Optional[str] = Field(default=None, sa_column=Column(Text))

    contact_email: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    idempotency_key: Optional[str] = Field(
        default=None,
        sa_column=Column(Text, index=True),
    )

    # ── Relationships ────────────────────────────────────────────────────────
    candidate_saved_jobs: List["CandidateSavedJob"] = Relationship(
        back_populates="job"
    )

    applications: List["JobApplication"] = Relationship(
        back_populates="job"
    )

    job_recommendations: List["JobRecommendation"] = Relationship(
        back_populates="job"
    )

    skills: List["JobSkill"] = Relationship(
        back_populates="job"
    )
