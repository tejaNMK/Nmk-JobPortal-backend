import uuid
from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now

from sqlalchemy import Column, DateTime, Index, Integer, Text, text
from sqlmodel import Field, SQLModel


class ContactUsInquiry(SQLModel, table=True):
    __tablename__ = "contact_us_inquiries"

    __table_args__ = (
        Index("idx_contact_us_email", "email"),
        Index("idx_contact_us_email_status", "email_status"),
        Index("idx_contact_us_created_at", "created_at"),
    )

    inquiry_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(Text, primary_key=True, nullable=False),
    )

    full_name: str = Field(
        sa_column=Column(Text, nullable=False)
    )

    email: str = Field(
        sa_column=Column(Text, nullable=False)
    )

    phone_number: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    inquiry_type: str = Field(
        sa_column=Column(Text, nullable=False)
    )

    custom_subject: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    message: str = Field(
        sa_column=Column(Text, nullable=False)
    )

    email_status: str = Field(
        default="PENDING",
        sa_column=Column(
            Text,
            nullable=False,
            server_default=text("'PENDING'")
        ),
    )

    retry_count: int = Field(
        default=0,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("0")
        ),
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        ),
    )

    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=utc_now,
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

    is_deleted: bool = Field(
        default=False,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("0"),
        ),
    )

    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )