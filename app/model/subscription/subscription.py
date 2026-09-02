from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
from app.utils.utc import utc_now_naive

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "subscription_type IN ('CANDIDATE', 'EMPLOYER', 'ADMIN')",
            name="ck_subscriptions_type",
        ),
        Index(
            "uq_subscriptions_name_lower",
            text("lower(subscription_name)"),
            unique=True,
        ),
        Index(
            "uq_subscriptions_one_active_default_type",
            text("upper(subscription_type)"),
            unique=True,
            postgresql_where=text("is_default = true AND is_active = true"),
        ),
    )

    subscription_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )

    subscription_name: str = Field(
        sa_column=Column(
            String(150),
            nullable=False,
        )
    )

    subscription_type: str = Field(
        sa_column=Column(
            String(30),
            nullable=False,
        )
    )

    description: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    price: Decimal = Field(
        default=0,
        sa_column=Column(
            Numeric(10, 2),
            nullable=False,
            server_default=text("0"),
        ),
    )

    currency: str = Field(
        default="INR",
        sa_column=Column(
            String(10),
            nullable=False,
            server_default=text("'INR'"),
        ),
    )

    duration_days: int = Field(
        default=30,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("30"),
        ),
    )

    billing_cycle: str = Field(
        default="Monthly",
        sa_column=Column(
            String(30),
            nullable=False,
            server_default=text("'Monthly'"),
        ),
    )

    display_order: int = Field(
        default=1,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default=text("1"),
        ),
    )

    max_published_jobs: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer),
    )

    max_job_alerts: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer),
    )

    max_resume_uploads: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer),
    )

    feature_flags: dict = Field(
        default_factory=dict,
        sa_column=Column(
            JSON,
            nullable=False,
            server_default=text("'{}'"),
        ),
    )

    is_featured: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
    )

    is_popular: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
    )

    is_active: bool = Field(
        default=True,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("true"),
        ),
    )

    is_default: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
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

    created_by: Optional[UUID] = Field(default=None)

    updated_by: Optional[UUID] = Field(default=None)
