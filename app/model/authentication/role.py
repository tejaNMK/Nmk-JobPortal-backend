from typing import List, Optional
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Boolean, Column, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import text

from app.model.authentication.mixins import TimeMixin
from app.model.authentication.user_role import UsersRole


class Role(SQLModel, TimeMixin, table=True):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("role_code", name="uq_roles_code"),
        {"extend_existing": True},
    )

    role_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()")
        )
    )

    role_name: str = Field(
        sa_column=Column(
            "role_name",
            String(100),
            nullable=False
        )
    )

    role_code: str = Field(
        sa_column=Column(
            "role_code",
            String(100),
            nullable=False
        )
    )

    role_description: Optional[str] = Field(
        default=None,
        sa_column=Column(Text)
    )

    active_flag: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true")
    )

    users: List["Users"] = Relationship(
        back_populates="roles",
        link_model=UsersRole
    )