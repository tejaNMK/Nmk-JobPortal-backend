from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import text
from sqlmodel import Field, Relationship, SQLModel

from app.model.authentication.mixins import TimeMixin
from app.model.authentication.user_role import UsersRole

if TYPE_CHECKING:
    from app.model.candidate_model.application_status_history import (
        ApplicationStatusHistory
    )
    from app.model.candidate_model.candidate_profile import (
        CandidateProfile
    )
    from app.model.candidate_model.message import (
        Message
    )


class Users(SQLModel, TimeMixin, table=True):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR mobile_number IS NOT NULL",
            name="chk_contact_method",
        ),
        CheckConstraint(
            "user_status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED', 'LOCKED')",
            name="chk_users_status",
        ),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("mobile_number", name="uq_users_mobile"),
        Index("idx_users_email", "email"),
        Index("idx_users_mobile", "mobile_number"),
        Index("idx_users_status", "user_status"),
        Index("idx_users_deleted_flag", "deleted_flag"),
        Index("idx_users_last_login", "last_login_at"),
    )

    user_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=text("gen_random_uuid()"),
        ),
    )

    first_name: str = Field(
        sa_column=Column(
            "first_name",
            String(100),
            nullable=False,
        )
    )

    # NOTE: middle_name column may not exist in older DB schemas/migrations.
    # Keep the ORM model forgiving by making this field optional and not required
    # for queries that don't select it.
    middle_name: Optional[str] = Field(
        default=None,
        sa_column=Column(
            "middle_name",
            String(100),
            nullable=True,
        ),
    )

    last_name: Optional[str] = Field(
        default=None,
        sa_column=Column(
            "last_name",
            String(100),
        ),
    )

    email: Optional[str] = Field(
        default=None,
        sa_column=Column(
            "email",
            String(255),
        ),
    )

    mobile_number: Optional[str] = Field(
        default=None,
        sa_column=Column(
            "mobile_number",
            String(20),
        ),
    )

    country_code: Optional[str] = Field(
        default="+91",
        sa_column=Column(
            "country_code",
            String(10),
        ),
    )

    phone_country_iso2: Optional[str] = Field(
        default=None,
        sa_column=Column(
            "phone_country_iso2",
            String(2),
        ),
    )

    password_hash: str = Field(
        sa_column=Column(
            "password_hash",
            String(255),
            nullable=False,
        )
    )

    profile_image_url: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    cover_image_url: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
    )

    user_status: str = Field(
        default="ACTIVE",
        sa_column=Column(
            "user_status",
            String(20),
            nullable=False,
            server_default="ACTIVE",
        ),
    )

    email_verified: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default="false",
        ),
    )

    mobile_verified: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default="false",
        ),
    )

    failed_login_attempts: int = Field(
        default=0,
        sa_column=Column(
            Integer,
            nullable=False,
            server_default="0",
        ),
    )

    account_locked: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default="false",
        ),
    )

    last_login_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    password_changed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    created_by: Optional[UUID] = Field(default=None)

    updated_by: Optional[UUID] = Field(default=None)

    deleted_flag: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default="false",
        ),
    )

    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime),
    )

    roles: List["Role"] = Relationship(
        back_populates="users",
        link_model=UsersRole,
    )

    candidate_profile: Optional["CandidateProfile"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"uselist": False},
    )

    application_status_changes: List["ApplicationStatusHistory"] = Relationship(
        back_populates="changed_by_user",
    )

    sent_messages: List["Message"] = Relationship(
        back_populates="sender",
        sa_relationship_kwargs={"foreign_keys": "Message.sender_id"},
    )

    received_messages: List["Message"] = Relationship(
        back_populates="receiver",
        sa_relationship_kwargs={"foreign_keys": "Message.receiver_id"},
    )