from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import text
from sqlmodel import Field, SQLModel


class EmailVerificationToken(SQLModel, table=True):
    __tablename__ = "email_verification_tokens"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )

    email: str = Field(
        sa_column=Column(String(255), nullable=False, index=True),
    )

    otp_hash: str = Field(
        sa_column=Column(String(255), nullable=False),
    )

    expires_at: datetime = Field(
        sa_column=Column(DateTime, nullable=False),
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
        ),
    )

    verified_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime, nullable=True),
    )

    is_used: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )

    __table_args__ = (
        Index("idx_evt_email_expires_at", "email", "expires_at"),
    )

