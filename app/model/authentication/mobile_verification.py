from datetime import datetime
import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Integer,
    Index,
    text
)
from sqlmodel import SQLModel, Field


class MobileVerification(SQLModel, table=True):
    __tablename__ = "mobile_verifications"

    __table_args__ = (
        Index(
            "idx_mobile_verification_phone",
            "country_code",
            "mobile_number"
        ),
    )

    verification_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True
    )

    country_code: str = Field(
        sa_column=Column(String(10), nullable=False)
    )

    mobile_number: str = Field(
        sa_column=Column(String(20), nullable=False)
    )

    otp_hash: str = Field(
        sa_column=Column(String(255), nullable=False)
    )

    is_verified: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false")
        )
    )

    attempt_count: int = Field(
        default=0,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("0")
        )
    )

    expires_at: datetime = Field(
        sa_column=Column(DateTime, nullable=False)
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP")
        )
    )