import uuid
from datetime import datetime
from typing import Optional
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, text
from sqlmodel import Field, SQLModel


class MasterJobCategory(SQLModel, table=True):
    __tablename__ = "master_job_categories"
    __table_args__ = (
        Index("idx_master_job_categories_name", "name", unique=True),
    )

    job_category_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(
            Text,
            primary_key=True,
            nullable=False,
            server_default=text("replace(gen_random_uuid()::text, '-', '')"),
        ),
    )

    name: str = Field(
        sa_column=Column(
            String(100),
            nullable=False,
        )
    )

    sort_order: int = Field(
        default=0,
        sa_column=Column(
            Integer,
            server_default=text("0"),
        ),
    )

    is_active: bool = Field(
        default=True,
        sa_column=Column(
            Boolean,
            server_default=text("true"),
        ),
    )

    created_at: datetime = Field(
        default_factory=utc_now_naive,
        sa_column=Column(
            DateTime,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )