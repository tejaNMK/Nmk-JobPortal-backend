from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class EmployerProfile(SQLModel, table=True):
    __tablename__ = "employer_profiles"

    id: str = Field(sa_column=Column(Text, primary_key=True, nullable=False))
    user_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.user_id"),
            nullable=False,
            unique=True,
        )
    )
    company_name: str = Field(sa_column=Column(Text, nullable=False))
    company_email: Optional[str] = Field(default=None, sa_column=Column(Text))
    company_mobile: Optional[str] = Field(default=None, sa_column=Column(Text))
    company_website: Optional[str] = Field(default=None, sa_column=Column(Text))
    company_logo_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    industry: Optional[str] = Field(default=None, sa_column=Column(Text))
    company_size: Optional[str] = Field(default=None, sa_column=Column(Text))
    company_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    company_location: Optional[str] = Field(default=None, sa_column=Column(Text))
    established_year: Optional[int] = Field(default=None, sa_column=Column(Integer))
    linkedin_url: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    website_url: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    gst_number: Optional[str] = Field(default=None, sa_column=Column(Text))
    registration_number: Optional[str] = Field(default=None, sa_column=Column(Text))
    job_title: Optional[str] = Field(default=None, sa_column=Column(String(150)))
    department: Optional[str] = Field(default=None, sa_column=Column(String(150)))
    bio: Optional[str] = Field(default=None, sa_column=Column(String(1000)))
    location: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    timezone: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    experience_years: Optional[int] = Field(default=None, sa_column=Column(Integer))
    candidate_response_time: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    interview_mode: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    availability: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    languages: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    profile_photo: Optional[str] = Field(default=None, sa_column=Column(Text))
    visibility: str = Field(
        default="PRIVATE",
        sa_column=Column(String(20), nullable=False, server_default=text("'PRIVATE'")),
    )
    specialization_1: Optional[str] = Field(default=None, sa_column=Column(String(150)))
    specialization_2: Optional[str] = Field(default=None, sa_column=Column(String(150)))
    specialization_3: Optional[str] = Field(default=None, sa_column=Column(String(150)))
    specialization_4: Optional[str] = Field(default=None, sa_column=Column(String(150)))
    is_verified: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    verification_status: str = Field(
        default="PENDING",
        sa_column=Column(String(20), nullable=False, server_default=text("'PENDING'")),
    )
    status: str = Field(
        default="ACTIVE",
        sa_column=Column(Text, nullable=False, server_default=text("'ACTIVE'")),
    )
    suspension_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    rejection_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    approved_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    rejected_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
    created_by: Optional[str] = Field(default=None, sa_column=Column(Text))
    updated_by: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_deleted: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )
    version: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
