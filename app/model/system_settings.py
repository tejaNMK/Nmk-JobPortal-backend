from datetime import datetime
from uuid import UUID, uuid4
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, Index, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class SystemSettings(SQLModel, table=True):
    __tablename__ = "system_settings"
    __table_args__ = (
        Index("idx_system_settings_is_active", "is_active"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )
    maintenance_mode: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    registration_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    default_subscription_plan: str | None = Field(
        default=None,
        sa_column=Column(String(150), nullable=True),
    )
    candidate_default_subscription_plan: str | None = Field(
        default=None,
        sa_column=Column(String(150), nullable=True),
    )
    employer_default_subscription_plan: str | None = Field(
        default=None,
        sa_column=Column(String(150), nullable=True),
    )
    password_policy: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    email_notifications: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    platform_config: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
    updated_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=utc_now_naive,
        ),
    )
    updated_by: str | None = Field(default=None, sa_column=Column(Text))
