from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlmodel import SQLModel, Field
from sqlalchemy import Boolean, Column, DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import text

from app.model.authentication.mixins import TimeMixin


class UsersRole(SQLModel, TimeMixin, table=True):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        {"extend_existing": True},
    )

    user_role_id: UUID = Field(
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

    role_id: UUID = Field(
        foreign_key="roles.role_id",
        nullable=False
    )

    assigned_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=func.now()
        )
    )

    assigned_by: Optional[UUID] = Field(default=None)

    active_flag: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true")
    )
