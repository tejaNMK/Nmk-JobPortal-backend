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
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class UserSubscription(SQLModel, table=True):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "role IN ('CANDIDATE', 'EMPLOYER', 'ADMIN')",
            name="ck_user_subscriptions_role",
        ),
        Index(
            "uq_user_subscriptions_razorpay_order_id",
            "razorpay_order_id",
            unique=True,
            postgresql_where=text("razorpay_order_id IS NOT NULL"),
        ),
        Index(
            "uq_user_subscriptions_razorpay_payment_id",
            "razorpay_payment_id",
            unique=True,
            postgresql_where=text("razorpay_payment_id IS NOT NULL"),
        ),
    )

    user_subscription_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )

    # User who owns this subscription
    user_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.user_id"),
            nullable=False,
        )
    )

    # Subscription Plan
    subscription_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("subscriptions.subscription_id"),
            nullable=False,
        )
    )

    role: str = Field(
        sa_column=Column(
            String(30),
            nullable=False,
            server_default=text("'CANDIDATE'"),
        )
    )

    # Subscription validity
    start_date: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    end_date: datetime = Field(
        sa_column=Column(
            DateTime,
            nullable=False,
        ),
    )

    # ACTIVE | EXPIRED | CANCELLED | PENDING
    status: str = Field(
        default="ACTIVE",
        sa_column=Column(
            String(20),
            nullable=False,
            server_default=text("'ACTIVE'"),
        ),
    )

    # FREE | PAID | REFUNDED | FAILED | PENDING
    payment_status: str = Field(
        default="PAID",
        sa_column=Column(
            String(20),
            nullable=False,
            server_default=text("'PAID'"),
        ),
    )

    # Price actually paid
    price_paid: Decimal = Field(
        default=0,
        sa_column=Column(
            Numeric(10, 2),
            nullable=False,
            server_default=text("0"),
        ),
    )

    # Discount applied
    discount_amount: Decimal = Field(
        default=0,
        sa_column=Column(
            Numeric(10, 2),
            nullable=False,
            server_default=text("0"),
        ),
    )

    # Currency
    currency: str = Field(
        default="INR",
        sa_column=Column(
            String(10),
            nullable=False,
            server_default=text("'INR'"),
        ),
    )

    # Payment Gateway Transaction Id
    transaction_reference: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String(255),
        ),
    )

    payment_gateway: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50)),
    )

    razorpay_order_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), index=True),
    )

    razorpay_payment_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), index=True),
    )

    payment_verified_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    # Invoice Number (future billing)
    invoice_number: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String(100),
        ),
    )

    # Auto Renewal
    auto_renew: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
    )

    cancelled_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    # Assigned manually by Super Admin
    assigned_by: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
        ),
    )

    # Internal notes
    remarks: Optional[str] = Field(
        default=None,
        sa_column=Column(
            Text,
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
