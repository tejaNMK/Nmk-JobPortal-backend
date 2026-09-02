from uuid import UUID, uuid4
from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import text
from sqlmodel import Field, SQLModel


class PasswordHistory(SQLModel, table=True):
    __tablename__ = "password_history"

    history_id: UUID = Field(
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

    password_hash: str = Field(
        sa_column=Column(
            "password_hash",
            String(500),
            nullable=False
        )
    )

    changed_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            nullable=False,
            server_default=func.now()
        )
    )
