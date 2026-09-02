from datetime import datetime
from typing import Optional
import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, text
from sqlmodel import Field, Relationship, SQLModel


class ApplicationNote(SQLModel, table=True):
    __tablename__ = "application_notes"

    note_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )

    application_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("job_applications.application_id"),
            nullable=False,
        )
    )

    note_text: str = Field(sa_column=Column(Text, nullable=False))

    # Who created the note — candidate themselves or system
    created_by: Optional[str] = Field(default=None, sa_column=Column(Text))

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=utc_now_naive,
        ),
    )

    is_deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean, server_default=text("false")),
    )

    deleted_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))

    # Relationships
    application: "JobApplication" = Relationship(back_populates="notes")
