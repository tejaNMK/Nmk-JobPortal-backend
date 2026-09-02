from datetime import date, datetime, time
from typing import Optional
import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Time,
    text,
)
from sqlmodel import Field, Relationship, SQLModel


class Interview(SQLModel, table=True):
    __tablename__ = "interviews"

    interview_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text(
                "replace(gen_random_uuid()::text, '-', '')"
            ),
        ),
    )

    # FK -> Job Application
    application_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("job_applications.application_id"),
            nullable=False,
        )
    )

    # Interview Details
    interview_title: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    round_number: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer),
    )

    interview_round: str = Field(
        sa_column=Column(
            Text,
            nullable=False,
        )
    )

    interview_date: date = Field(
        sa_column=Column(
            Date,
            nullable=False,
        )
    )

    interview_time: time = Field(
        sa_column=Column(
            Time,
            nullable=False,
        )
    )

    end_time: Optional[time] = Field(
        default=None,
        sa_column=Column(Time),
    )

    timezone: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    mode: str = Field(
        sa_column=Column(
            Text,
            nullable=False,
        )
    )

    # Required only for Online interviews
    meeting_link: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    # Required only for Offline interviews
    interview_location: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    # Supports a single interviewer for now.
    # We'll later normalize this into a mapping table
    # when panel interviews are implemented.
    interviewer_name: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    status: str = Field(
        default="SCHEDULED",
        sa_column=Column(
            Text,
            nullable=False,
            server_default=text("'SCHEDULED'"),
        ),
    )

    remarks: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(
            DateTime,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=utc_now_naive,
        ),
    )

    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    @property
    def scheduled_at(self) -> Optional[datetime]:
        if not self.interview_date or not self.interview_time:
            return None
        return datetime.combine(self.interview_date, self.interview_time)

    @property
    def location_or_link(self) -> Optional[str]:
        return self.meeting_link or self.interview_location

    application: Optional["JobApplication"] = Relationship(
        back_populates="interviews"
    )
