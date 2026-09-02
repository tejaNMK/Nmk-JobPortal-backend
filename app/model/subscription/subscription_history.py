from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class SubscriptionHistory(SQLModel, table=True):
    __tablename__ = "subscription_history"

    history_id: UUID = Field(
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

    subscription_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("subscriptions.subscription_id"),
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

    action: str = Field(sa_column=Column(String(30), nullable=False))
    performed_by: Optional[UUID] = Field(default=None, sa_column=Column(PG_UUID(as_uuid=True)))
    old_start_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    old_end_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    new_start_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    new_end_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime))
    remarks: Optional[str] = Field(default=None, sa_column=Column(Text))

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
