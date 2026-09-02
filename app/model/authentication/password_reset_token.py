from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import text
from sqlmodel import Field, SQLModel


class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "password_reset_tokens"

    token_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()")
        )
    )

    user_id: UUID = Field(
        foreign_key="users.user_id",
        nullable=False
    )

    reset_token_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(String(500))
    )

    otp_code_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(String(500))
    )

    expires_at: datetime = Field(
        sa_column=Column(DateTime, nullable=False)
    )

    used_flag: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false")
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=func.now()
        )
    )
