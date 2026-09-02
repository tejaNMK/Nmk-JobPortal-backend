from datetime import datetime
from uuid import UUID, uuid4
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class SubscriptionUsage(SQLModel, table=True):
    __tablename__ = "subscription_usage"
    __table_args__ = (
        UniqueConstraint(
            "user_subscription_id",
            "feature_name",
            "period_start",
            "period_end",
            name="uq_subscription_usage_feature",
        ),
    )

    usage_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )

    user_subscription_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("user_subscriptions.user_subscription_id"),
            nullable=False,
        )
    )

    user_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.user_id"),
            nullable=False,
        )
    )

    feature_name: str = Field(sa_column=Column(String(100), nullable=False))
    period_start: datetime = Field(
        default_factory=lambda: datetime(1970, 1, 1),
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("'1970-01-01 00:00:00'"),
        ),
    )
    period_end: datetime = Field(
        default_factory=lambda: datetime(9999, 12, 31, 23, 59, 59),
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("'9999-12-31 23:59:59'"),
        ),
    )
    used_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
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
