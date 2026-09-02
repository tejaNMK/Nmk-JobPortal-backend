from datetime import datetime
from typing import Optional
from uuid import UUID

import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class ProfileViewEvent(SQLModel, table=True):
    """Records each time a recruiter or visitor views a candidate profile."""

    __tablename__ = "profile_view_events"

    __table_args__ = (
        Index("idx_pve_candidate_id", "candidate_id"),
        Index("idx_pve_viewed_at", "viewed_at"),
    )

    view_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )

    candidate_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("candidate_profiles.candidate_id"),
            nullable=False,
        )
    )

    viewer_user_id: Optional[UUID] = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.user_id"),
            nullable=True,
        ),
    )

    viewer_ip: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    viewed_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )