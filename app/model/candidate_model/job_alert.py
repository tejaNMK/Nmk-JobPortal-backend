from datetime import datetime
from typing import Optional
import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, text
from sqlmodel import Field, Relationship, SQLModel


class JobAlert(SQLModel, table=True):
    __tablename__ = "job_alerts"

    alert_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )

    candidate_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("candidate_profiles.candidate_id"),
            nullable=False,
        )
    )

    # New fields
    title: Optional[str] = Field(
        default=None,
        sa_column=Column("job_alert_title", String(100)),
    )

    job_category: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
    )

    job_title: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
    )

    preferred_location: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100)),
    )

    experience_level: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50)),
    )

    employment_type: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50)),
    )

    notification_preference: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50)),
    )

    frequency: Optional[str] = Field(
        default="DAILY",
        sa_column=Column("alert_frequency", String(30)),
    )

    timezone: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
    )

    is_active: bool = Field(
        default=True,
        sa_column=Column(
            "active_status",
            Boolean,
            server_default=text("true"),
        ),
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    candidate: "CandidateProfile" = Relationship(
        back_populates="job_alerts"
    )

