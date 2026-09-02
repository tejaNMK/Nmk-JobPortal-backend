import uuid
from datetime import datetime
from app.utils.utc import utc_now_naive

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlmodel import Field, SQLModel


class MasterSalaryExpectation(SQLModel, table=True):
    __tablename__ = "master_salary_expectations"
    __table_args__ = (
        Index(
            "idx_master_salary_expectations_country_label",
            text("COALESCE(country_id, '')"),
            "label",
            unique=True,
        ),
    )

    salary_expectation_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        sa_column=Column(Text, primary_key=True, nullable=False, server_default=text("replace(gen_random_uuid()::text, '-', '')")),
    )
    # NULL = country-agnostic default band shown for any country that
    # doesn't have its own dedicated salary bands (e.g. "$50K - $70K").
    # Set = bands specific to that country (e.g. India's "3-5 LPA").
    country_id: str | None = Field(default=None, sa_column=Column(Text, ForeignKey("master_countries.country_id"), nullable=True))
    label: str = Field(sa_column=Column(String(150), nullable=False))
    sort_order: int = Field(default=0, sa_column=Column(Integer, server_default=text("0")))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, server_default=text("true")))
    created_at: datetime = Field(default_factory=utc_now_naive, sa_column=Column(DateTime, server_default=text("CURRENT_TIMESTAMP")))