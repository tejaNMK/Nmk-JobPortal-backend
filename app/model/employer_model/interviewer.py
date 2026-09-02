from datetime import datetime
import uuid
from app.utils.utc import utc_now_naive

from sqlalchemy import Column, DateTime, Text, text
from sqlmodel import Field, SQLModel


class Interviewer(SQLModel, table=True):
    __tablename__ = "interviewers"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )

    name: str = Field(sa_column=Column(Text, nullable=False))

    email: str = Field(sa_column=Column(Text, nullable=False, unique=True))

    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )

    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime,
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=utc_now_naive,
        ),
    )
