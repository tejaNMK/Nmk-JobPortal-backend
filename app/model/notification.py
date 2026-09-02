from __future__ import annotations

from datetime import datetime
import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    JSON,
    String,
    Text,
    text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "recipient_user_id",
            "event_key",
            name="uq_notifications_recipient_event_key",
        ),
        Index(
            "idx_notifications_recipient_read_created",
            "recipient_user_id",
            "is_read",
            "created_at",
        ),
        Index(
            "idx_notifications_recipient_type_created",
            "recipient_user_id",
            "notification_type",
            "created_at",
        ),
    )

    notification_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )

    recipient_id: str = Field(
        sa_column=Column(
            Text,
            nullable=False,
            index=True,
        )
    )

    recipient_user_id: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            nullable=True,
            index=True,
        ),
    )

    recipient_role: str | None = Field(
        default=None,
        sa_column=Column(
            String(100),
            nullable=True,
        ),
    )

    title: str = Field(
        sa_column=Column(
            String(255),
            nullable=False,
        )
    )

    message: str = Field(
        sa_column=Column(
            Text,
            nullable=False,
        )
    )

    notification_type: str = Field(
        sa_column=Column(
            String(50),
            nullable=False,
        )
    )

    reference_type: str | None = Field(
        default=None,
        sa_column=Column(
            String(50),
        ),
    )

    reference_id: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
        ),
    )

    entity_type: str | None = Field(
        default=None,
        sa_column=Column(
            String(50),
            nullable=True,
        ),
    )

    entity_id: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            nullable=True,
        ),
    )

    target_route: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            nullable=True,
        ),
    )

    metadata_: dict | None = Field(
        default=None,
        sa_column=Column(
            "metadata",
            JSON,
            nullable=True,
        ),
    )

    event_key: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            nullable=True,
        ),
    )

    is_read: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
    )

    read_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime),
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
        ),
    )
