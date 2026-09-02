from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class ActivityLog(SQLModel, table=True):
    """Central platform audit log consumed by Super Admin."""

    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("idx_activity_logs_actor_id", "actor_id"),
        Index("idx_activity_logs_actor_role", "actor_role"),
        Index("idx_activity_logs_action", "action"),
        Index("idx_activity_logs_entity_type", "entity_type"),
        Index("idx_activity_logs_created_at", "created_at"),
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
    actor_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.user_id"),
            nullable=True,
        ),
    )
    actor_role: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
    )
    action: str = Field(sa_column=Column(String(100), nullable=False))
    entity_type: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
    )
    entity_id: Optional[str] = Field(default=None, sa_column=Column(Text))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    target_entity_name: Optional[str] = Field(default=None, sa_column=Column(Text))
    ip_address: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
    )
    metadata_: Optional[dict] = Field(
        default=None,
        sa_column=Column("metadata", JSONB, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
