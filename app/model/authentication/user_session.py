from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import text
from sqlmodel import Field, SQLModel


class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint(
            "login_method IN ('EMAIL', 'MOBILE')",
            name="chk_login_method"
        ),
        CheckConstraint(
            "session_status IN ('ACTIVE', 'LOGGED_OUT', 'EXPIRED')",
            name="chk_session_status"
        ),
        Index("idx_user_sessions_user", "user_id"),
        Index("idx_user_sessions_status", "session_status"),
        Index("idx_user_sessions_login_at", "login_at"),
    )

    session_id: UUID = Field(
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

    jwt_id: str = Field(
        sa_column=Column(
            "jwt_id",
            String(255),
            nullable=False
        )
    )

    refresh_token_hash: Optional[str] = Field(
        default=None,
        sa_column=Column(String(500))
    )

    login_method: str = Field(
        sa_column=Column(
            "login_method",
            String(20),
            nullable=False
        )
    )

    ip_address: Optional[str] = Field(
        default=None,
        sa_column=Column(String(45))
    )

    user_agent: Optional[str] = Field(
        default=None,
        sa_column=Column(Text)
    )

    device_type: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100))
    )

    login_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=func.now()
        )
    )

    logout_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime)
    )

    session_status: str = Field(
        default="ACTIVE",
        sa_column=Column(
            "session_status",
            String(20),
            nullable=False,
            server_default="ACTIVE"
        )
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=func.now()
        )
    )
