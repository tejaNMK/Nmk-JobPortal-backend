from datetime import datetime
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING

import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel
from uuid import UUID
from app.utils.utc import utc_now_naive

if TYPE_CHECKING:
    from app.model.authentication.users import Users
    from app.model.candidate_model.candidate_resume_detail import CandidateResumeDetail
    from app.model.candidate_model.candidate_resume import CandidateResume
    from app.model.candidate_model.candidate_saved_job import CandidateSavedJob
    from app.model.candidate_model.candidate_saved_search import CandidateSavedSearch
    from app.model.candidate_model.job_application import JobApplication
    from app.model.candidate_model.job_alert import JobAlert
    from app.model.candidate_model.job_recommendation import JobRecommendation
    from app.model.candidate_model.candidate_company_following import CandidateCompanyFollowing

class CandidateProfile(SQLModel, table=True):
    __tablename__ = "candidate_profiles"
    __table_args__ = (Index("idx_candidate_profiles_user", "user_id"),)

    candidate_id: str = Field(default_factory=lambda: uuid.uuid4().hex, sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")))
    user_id: UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), unique=True, nullable=False))
    headline: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    total_experience: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))
    current_location: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    preferred_location: Optional[str] = Field(default=None, sa_column=Column(String(255)))

    # Country + dependent location dropdowns (master_countries / master_locations).
    # current_location / preferred_location above are kept in sync as display-name
    # caches so existing readers of those text columns keep working.
    country_id: Optional[str] = Field(default=None, sa_column=Column(Text, ForeignKey("master_countries.country_id")))
    primary_location_id: Optional[str] = Field(default=None, sa_column=Column(Text, ForeignKey("master_locations.location_id")))
    preferred_location_id: Optional[str] = Field(default=None, sa_column=Column(Text, ForeignKey("master_locations.location_id")))

    website_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    portfolio_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    skills_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    linkedin_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    github_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    dribbble_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    twitter_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    profile_completion_pct: int = Field(default=0, sa_column=Column(Integer, server_default=text("0")))
    application_count: int = Field(default=0, sa_column=Column(Integer, server_default=text("0")))
    active_resume_id: Optional[str] = Field(default=None, sa_column=Column(Text))
    profile_visibility: str = Field(default="PRIVATE", sa_column=Column(String(20), server_default=text("'PRIVATE'")))
    searchable_flag: bool = Field(default=True, sa_column=Column(Boolean, server_default=text("true")))
    open_to_work: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))
    search_engine_indexing: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false")))

    # "Notify me" toggle on the My Followings page — alerts the candidate when a
    # followed company posts a new job.
    follow_notifications_enabled: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false")))

    # Professional-snapshot fields (used by PATCH /candidate/profile/professional-snapshot)
    experience_level: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    current_company: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    notice_period: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    notice_period_id: Optional[str] = Field(default=None, sa_column=Column(Text, ForeignKey("master_notice_periods.notice_period_id")))
    desired_employment: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    salary_expectation: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    salary_expectation_id: Optional[str] = Field(default=None, sa_column=Column(Text, ForeignKey("master_salary_expectations.salary_expectation_id")))
    current_ctc: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2)))
    expected_ctc: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2)))
    work_preference: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    target_roles: Optional[str] = Field(default=None, sa_column=Column(Text))
    status: str = Field(default="ACTIVE", sa_column=Column(String(20), server_default=text("'ACTIVE'")))
    suspension_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))
    updated_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), onupdate=utc_now_naive))
    created_by: Optional[str] = Field(default=None, sa_column=Column(Text))
    updated_by: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_deleted: bool = Field(default=False, sa_column=Column(Boolean, server_default=text("false")))
    deleted_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    deleted_by: Optional[str] = Field(default=None, sa_column=Column(Text))

    user: Optional["Users"] = Relationship(back_populates="candidate_profile")
    resume_details: List["CandidateResumeDetail"] = Relationship(back_populates="candidate")
    resumes: List["CandidateResume"] = Relationship(back_populates="candidate")
    saved_jobs: List["CandidateSavedJob"] = Relationship(back_populates="candidate")
    saved_searches: List["CandidateSavedSearch"] = Relationship(back_populates="candidate")
    applications: List["JobApplication"] = Relationship(back_populates="candidate")
    job_alerts: List["JobAlert"] = Relationship(back_populates="candidate")
    job_recommendations: List["JobRecommendation"] = Relationship(back_populates="candidate")
    company_followings: List["CandidateCompanyFollowing"] = Relationship(back_populates="candidate")
