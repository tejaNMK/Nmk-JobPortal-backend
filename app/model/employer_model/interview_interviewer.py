from datetime import datetime

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Column, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel


class InterviewInterviewer(SQLModel, table=True):
    __tablename__ = "interview_interviewers"
    __table_args__ = (
        UniqueConstraint(
            "interview_id",
            "interviewer_id",
            name="uq_interview_interviewers_interview_interviewer",
        ),
    )

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )

    interview_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("interviews.interview_id"),
            nullable=False,
        )
    )

    interviewer_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("interviewers.id"),
            nullable=False,
        )
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
