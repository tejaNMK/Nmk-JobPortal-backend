from datetime import datetime
from typing import Optional

import uuid
from app.utils.utc import utc_now_naive
from sqlalchemy import Column, DateTime, ForeignKey, JSON, Text, text
from sqlmodel import Field, SQLModel


class InterviewHistory(SQLModel, table=True):
    __tablename__ = "interview_history"

    history_id: str = Field(
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

    interview_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("interviews.interview_id"),
            nullable=False,
        )
    )

    application_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("job_applications.application_id"),
            nullable=False,
        )
    )

    employer_id: str = Field(sa_column=Column(Text, nullable=False))

    performed_by: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    action: str = Field(sa_column=Column(Text, nullable=False))

    timestamp: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    previous_values: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
    )

    new_values: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
    )
