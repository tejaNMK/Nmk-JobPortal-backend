from __future__ import annotations

from datetime import datetime
import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, SQLModel


class JobAlertNotificationDelivery(SQLModel, table=True):
    __tablename__ = "job_alert_notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "delivery_key",
            name="uq_job_alert_notification_deliveries_delivery_key",
        ),
        CheckConstraint(
            "channel IN ('EMAIL', 'IN_APP')",
            name="chk_job_alert_notification_deliveries_channel",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')",
            name="chk_job_alert_notification_deliveries_status",
        ),
        Index(
            "idx_job_alert_notification_deliveries_recipient",
            "recipient_id",
        ),
        Index(
            "idx_job_alert_notification_deliveries_alert",
            "alert_id",
        ),
        Index(
            "idx_job_alert_notification_deliveries_status",
            "status",
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

    candidate_id: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            ForeignKey("candidate_profiles.candidate_id"),
            nullable=True,
        ),
    )

    recipient_id: str = Field(sa_column=Column(Text, nullable=False))

    alert_id: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            ForeignKey("job_alerts.alert_id"),
            nullable=True,
        ),
    )

    job_id: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            ForeignKey("jobs.job_id"),
            nullable=True,
        ),
    )

    frequency: str = Field(sa_column=Column(String(30), nullable=False))

    notification_type: str = Field(sa_column=Column(String(50), nullable=False))

    channel: str = Field(sa_column=Column(String(20), nullable=False))

    delivery_key: str = Field(sa_column=Column(Text, nullable=False))

    window_start: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime, nullable=True),
    )

    window_end: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime, nullable=True),
    )

    status: str = Field(sa_column=Column(String(20), nullable=False))

    attempt_count: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default=text("1")),
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    sent_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime, nullable=True),
    )

    failed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime, nullable=True),
    )

    last_error: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
